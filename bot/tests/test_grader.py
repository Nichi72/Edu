# -*- coding: utf-8 -*-
"""채점 엔진 테스트. fixtures/ 는 이 저장소의 cp-XX 태그에서 뽑은 작은 프로젝트 조각이다."""
import io
import pathlib
import sys
import zipfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from grader import csharp, unityyaml  # noqa: E402
from grader.bundle import Bundle, BundleError  # noqa: E402
from grader.compare import Comparer, evaluate, prefix, sort_key  # noqa: E402
from grader.report import student_message, teacher_line  # noqa: E402

FX = pathlib.Path(__file__).resolve().parent / "fixtures"


def fx(tag: str) -> Bundle:
    return Bundle.from_path(FX / tag)


def zip_of(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


# ───────────────────────── csharp ─────────────────────────
def test_norm_drops_numbers_strings_and_spaces():
    assert csharp.norm('transform.position += new Vector3(0f, -fallSpeed, 0.5f);') == \
        'transform.position+=new Vector3(N,-fallSpeed,N);'
    assert csharp.norm('Debug.Log("hi" + 3)') == 'Debug.Log("S"+N)' or csharp.norm(csharp.strip('Debug.Log("hi" + 3)')) == 'Debug.Log("S"+N)'
    assert "Vector3" in csharp.norm("new Vector3(1,2,3)")          # 식별자 속 숫자는 안 건드린다


def test_parse_fields_methods_and_statements():
    src = '''
    using UnityEngine;
    // 주석 속 class Fake { }
    public class BirdMove : MonoBehaviour
    {
        public float gravity = 5f; // 중력
        [SerializeField] float hidden = 1f;
        float speed = 5f, jump = 3f;
        public int Score { get; set; }
        void Start() { Debug.Log("시작"); }
        void Update()
        {
            if (Keyboard.current.spaceKey.wasPressedThisFrame) { transform.Translate(Vector3.up * jump * Time.deltaTime); }
            else transform.Translate(gravity * Vector3.down * Time.deltaTime);
            for (int i = 0; i < 3; i++) { speed += 1; }
        }
        int Twice(int x) => x * 2;
    }
    '''
    f = csharp.parse(src, "BirdMove.cs")
    c = f.classes["BirdMove"]
    assert f.usings == {"UnityEngine"}
    assert c.base == "MonoBehaviour"
    assert c.fields["gravity"].serialized and c.fields["gravity"].type == "float"
    assert c.fields["hidden"].serialized                      # [SerializeField]
    assert not c.fields["speed"].serialized and "jump" in c.fields
    assert "Score" in c.properties and "Score" not in c.fields
    assert set(c.methods) == {"Start", "Update", "Twice"}
    assert c.methods["Update"].statements == [
        "if(Keyboard.current.spaceKey.wasPressedThisFrame)",
        "transform.Translate(Vector3.up*jump*Time.deltaTime)",
        "else transform.Translate(gravity*Vector3.down*Time.deltaTime)",
        "for(int i=N;i<N;i++)",
        "speed+=N",
    ]
    assert c.methods["Twice"].statements == ["x*N"]


def test_parse_ignores_comments_and_strings_with_braces():
    src = 'public class A : MonoBehaviour { string s = "}{"; /* { */ void Update() { x = \'{\'; } }'
    c = csharp.parse(src).classes["A"]
    assert "s" in c.fields and c.methods["Update"].statements == ["x='C'"]


# ───────────────────────── bundle ─────────────────────────
def test_bundle_rejects_non_zip_and_missing_assets():
    with pytest.raises(BundleError):
        Bundle.from_zip_bytes(b"not a zip")
    with pytest.raises(BundleError):
        Bundle.from_zip_bytes(zip_of({"readme.txt": b"x"}))


def test_bundle_strips_root_folder_and_junk():
    data = zip_of({
        "MyProject/Assets/Scripts/A.cs": b"public class A {}",
        "MyProject/Library/junk.bin": b"0" * 10,
        "MyProject/Assets/Textures/big.png": b"0",
        "../evil.cs": b"",
        "MyProject/ProjectSettings/ProjectSettings.asset": b"PlayerSettings:\n  activeInputHandler: 2\n",
    })
    b = Bundle.from_zip_bytes(data)
    assert b.scripts() == ["Assets/Scripts/A.cs"]
    assert not any("Library" in p or "png" in p or "evil" in p for p in b.files)
    assert b.project_setting("activeInputHandler") == "2"


def test_bundle_excludes_editor_scripts():
    b = Bundle.from_zip_bytes(zip_of({"Assets/Editor/Tool.cs": b"class T{}", "Assets/Scripts/A.cs": b"class A{}"}))
    assert b.scripts() == ["Assets/Scripts/A.cs"]


# ───────────────────────── unityyaml ─────────────────────────
def test_scene_objects_components_and_script_names():
    b = fx("cp-07")
    uf = unityyaml.build(b.text("Assets/Scenes/SampleScene.unity"), "SampleScene.unity", b.guid_map())
    bird = uf.objects["Bird"]
    assert [c.key for c in bird.comps] == ["Transform", "MeshFilter", "BoxCollider", "MeshRenderer", "BirdMove"]
    cam = uf.objects["Main Camera"]
    camera = next(c for c in cam.comps if c.key == "Camera")
    assert unityyaml.value_at(camera.data, "orthographic size") == 5
    assert unityyaml.value_at(next(c for c in cam.comps if c.key == "Transform").data, "m_LocalPosition") == \
        {"x": 0, "y": 0, "z": -10}


def test_prefab_paths_follow_hierarchy():
    b = fx("cp-12")
    uf = unityyaml.build(b.text("Assets/Prefabs/PipePair.prefab"), "PipePair.prefab", b.guid_map())
    assert {"PipePair", "PipePair/PipeTop", "PipePair/PipeBottom"} <= set(uf.objects)
    assert "PipeMove" in [c.key for c in uf.objects["PipePair"].comps]


# ───────────────────────── compare ─────────────────────────
def test_same_state_passes_and_earlier_state_fails():
    cmp = Comparer()
    assert cmp.compare(fx("cp-06"), fx("cp-06"), "cp-06").ok
    r = cmp.compare(fx("cp-06"), fx("cp-05"), "cp-06")
    assert not r.ok and any("Update() 가 없다" in f.student for f in r.findings)


def test_missing_public_field_and_statement_are_reported_without_code():
    r = Comparer().compare(fx("cp-07"), fx("cp-06"), "cp-07")
    msgs = [f.student for f in r.findings]
    assert any("변수 fallSpeed" in m for m in msgs)
    assert any("빠진 문장 1개" in m for m in msgs)
    assert not any("Time.deltaTime" in m for m in msgs)          # 학생 문장에는 코드가 없다
    assert any("Time.deltaTime" in f.teacher for f in r.findings)  # 선생님 상세에는 있다


def test_extra_student_work_is_ignored_and_ignored_statements_skip():
    ref = Bundle.from_zip_bytes(zip_of({
        "Assets/Scripts/A.cs": b"using UnityEngine; public class A : MonoBehaviour { void Update() { Debug.Log(1); x += 1; } }",
    }))
    sub = Bundle.from_zip_bytes(zip_of({
        "Assets/Scripts/A.cs": b"using UnityEngine; using System; public class A : MonoBehaviour { int y; void Update() { x += 2; y++; } void Start() {} }",
    }))
    assert Comparer().compare(ref, sub).ok


def test_private_instead_of_public_is_flagged():
    ref = Bundle.from_zip_bytes(zip_of({"Assets/Scripts/A.cs": b"public class A { public float speed = 1f; }"}))
    sub = Bundle.from_zip_bytes(zip_of({"Assets/Scripts/A.cs": b"public class A { float speed = 1f; }"}))
    r = Comparer().compare(ref, sub)
    assert [f.student for f in r.findings] == ["A: 변수 speed 이(가) Inspector 에 안 보인다 (public 이 아니다)"]


def test_scene_component_and_prefab_missing():
    r = Comparer().compare(fx("cp-12"), fx("cp-10"), "cp-12")
    areas = {f.area for f in r.findings}
    assert {"스크립트", "씬", "프리팹", "머티리얼"} <= areas


def test_value_rule_detects_camera_change():
    b = fx("cp-07")
    scene = b.text("Assets/Scenes/SampleScene.unity").replace("orthographic size: 5", "orthographic size: 7")
    files = dict(b.files)
    files["Assets/Scenes/SampleScene.unity"] = scene.encode("utf-8")
    sub = Bundle(files=files)
    r = Comparer().compare(b, sub)
    assert [f.student for f in r.findings] == ["Main Camera 의 Size 값을 5 에 맞춘다 (지금 7)"]
    assert "(Camera orthographic size)" in r.findings[0].teacher


def test_value_rule_shows_inspector_name_and_value():
    b = fx("cp-07")
    scene = b.text("Assets/Scenes/SampleScene.unity")
    assert scene.count("m_LocalPosition: {x: 0, y: 0, z: -10}") == 1          # 카메라만 z -10
    scene = scene.replace("m_LocalPosition: {x: 0, y: 0, z: -10}", "m_LocalPosition: {x: 2, y: 1.5, z: -10}")
    scene = scene.replace("orthographic: 1", "orthographic: 0")
    files = dict(b.files)
    files["Assets/Scenes/SampleScene.unity"] = scene.encode("utf-8")
    r = Comparer().compare(b, Bundle(files=files))
    assert sorted(f.student for f in r.findings) == [
        "Main Camera 의 Position 값을 (0, 0, -10) 에 맞춘다 (지금 (2, 1.5, -10))",
        "Main Camera 의 Projection 값을 Orthographic 에 맞춘다 (지금 Perspective)",
    ]


def test_fmt_value():
    from grader.compare import _field_label, _fmt_value
    assert _fmt_value("orthographic size", 5.0) == "5" and _fmt_value("", 0.5) == "0.5"
    assert _fmt_value("", 0.12345) == "0.123" and _fmt_value("", None) == "없음"
    assert _fmt_value("m_LocalScale", {"x": 1, "y": 1, "z": 1}) == "(1, 1, 1)"
    assert _field_label("m_TaaSettings.m_Quality") == "TaaSettings.Quality"


# ───────────────────────── progress / report ─────────────────────────
def test_progress_reached_is_highest_pass_not_consecutive():
    refs = [(t, fx(t)) for t in ("cp-05", "cp-06", "cp-07")]
    p = evaluate(refs, fx("cp-07"), Comparer(), "cp-07")
    assert p.reached == "cp-07" and p.target_ok
    assert not p.results[1].ok                        # cp-06 의 문장은 cp-07 에서 바뀌었다 — 그래도 도달은 cp-07
    p2 = evaluate(refs, fx("cp-06"), Comparer(), "cp-07")
    assert p2.reached == "cp-06" and not p2.target_ok
    msg = student_message(p2, nth=2, when="14:52")
    assert "도달한 진도: cp-06" in msg and "cp-07 ❌" in msg and "미통과" in msg
    assert "통과" in teacher_line("홍길동", p, nth=1)


def test_sort_key_and_prefix_chain():
    assert sorted(["cp-10", "cp-2", "cp-07"], key=sort_key) == ["cp-2", "cp-07", "cp-10"]
    assert sorted(["10일차", "2일차", "7일차"], key=sort_key) == ["2일차", "7일차", "10일차"]
    assert prefix("7일차") == prefix("10일차") != prefix("과제1")
    refs = [("cp-06", fx("cp-06")), ("hw-01", fx("cp-07"))]
    p = evaluate(refs, fx("cp-07"), Comparer(), "hw-01")
    assert [r.cp for r in p.results] == ["hw-01"] and p.target_ok
    # 한글 이름: 같은 계열(일차)만, 과녁 이하만 본다. 과녁이 없으면 전부 본다
    refs = [("6일차", fx("cp-06")), ("7일차", fx("cp-07")), ("10일차", fx("cp-10")), ("과제1", fx("cp-12"))]
    p = evaluate(refs, fx("cp-07"), Comparer(), "7일차")
    assert [r.cp for r in p.results] == ["6일차", "7일차"] and p.reached == "7일차"
    assert {r.cp for r in evaluate(refs, fx("cp-07"), Comparer(), None).results} == {"6일차", "7일차", "10일차", "과제1"}


def test_student_message_without_target_names_next_item():
    # 과녁이 없고 통과한 것도 없을 때, 다음 항목을 고르는 줄이 sort_key 를 쓴다 (한때 import 가 빠져 있었다)
    from grader.report import student_message
    refs = [("cp-06", fx("cp-06")), ("cp-10", fx("cp-10"))]
    p = evaluate(refs, fx("cp-07"), Comparer(), None)
    text = student_message(p, nth=1, when="10/28 20:00")
    assert "cp-06" in text and "❌" in text
