using System;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace ClassRecorder
{
    /// <summary>
    /// 메뉴 「기록」 과 작은 상태 창. 수업 중엔 이 창만 한쪽에 띄워 두면 된다.
    /// </summary>
    public class ChangeRecorderWindow : EditorWindow
    {
        [MenuItem("기록/창 열기", false, 1)]
        public static void Open()
        {
            var w = GetWindow<ChangeRecorderWindow>("수업 기록");
            w.minSize = new Vector2(360, 240);
            w.Show();
        }

        [MenuItem("기록/시작", false, 20)]
        static void StartMenu() { ChangeRecorder.StartSession(); Open(); }
        [MenuItem("기록/시작", true)]
        static bool StartMenuValid() => !ChangeRecorder.IsRecording;

        [MenuItem("기록/끝", false, 21)]
        static void StopMenu()
        {
            if (EditorUtility.DisplayDialog("수업 기록", "기록을 끝낼까요?\n" + ChangeRecorder.SessionDir, "끝", "계속 기록"))
                ChangeRecorder.StopSession("menu");
        }
        [MenuItem("기록/끝", true)]
        static bool StopMenuValid() => ChangeRecorder.IsRecording;

        [MenuItem("기록/마커 %#m", false, 40)]
        static void MarkerMenu()
        {
            if (!ChangeRecorder.IsRecording) { ShowNotificationAll("기록 중이 아닙니다"); return; }
            ChangeRecorder.Marker("");
            ShowNotificationAll("마커 " + ChangeRecorder.MarkerCount);
        }

        [MenuItem("기록/폴더 열기", false, 60)]
        static void OpenFolder()
        {
            var dir = ChangeRecorder.IsRecording ? ChangeRecorder.SessionDir : ChangeRecorder.LastSessionDir;
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) { EditorUtility.DisplayDialog("수업 기록", "아직 기록한 세션이 없습니다.", "확인"); return; }
            EditorUtility.RevealInFinder(dir + "/events.jsonl");
        }

        static void ShowNotificationAll(string msg)
        {
            foreach (var w in Resources.FindObjectsOfTypeAll<ChangeRecorderWindow>()) w.ShowNotification(new GUIContent(msg));
            // 창이 안 열려 있으면 Scene 뷰에 띄운다
            if (SceneView.lastActiveSceneView != null) SceneView.lastActiveSceneView.ShowNotification(new GUIContent(msg));
        }

        string markerText = "";
        Vector2 scroll;
        double lastRepaint;
        GUIStyle mono;

        void OnEnable()
        {
            ChangeRecorder.Changed += Repaint;
            EditorApplication.update += Tick;
        }

        void OnDisable()
        {
            ChangeRecorder.Changed -= Repaint;
            EditorApplication.update -= Tick;
        }

        void Tick()
        {
            if (!ChangeRecorder.IsRecording) return;
            if (EditorApplication.timeSinceStartup - lastRepaint < 0.5) return;
            lastRepaint = EditorApplication.timeSinceStartup;
            Repaint();
        }

        void OnGUI()
        {
            if (mono == null) mono = new GUIStyle(EditorStyles.label) { font = EditorStyles.miniFont, fontSize = 11, wordWrap = false };

            EditorGUILayout.Space(6);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (ChangeRecorder.IsRecording)
                {
                    var elapsed = DateTime.Now - ChangeRecorder.StartTime;
                    var old = GUI.color; GUI.color = new Color(1f, 0.35f, 0.3f);
                    GUILayout.Label("●", GUILayout.Width(16));
                    GUI.color = old;
                    GUILayout.Label("기록 중   " + elapsed.ToString(@"hh\:mm\:ss") + "   사건 " + ChangeRecorder.Seq + "   마커 " + ChangeRecorder.MarkerCount, EditorStyles.boldLabel);
                    GUILayout.FlexibleSpace();
                    if (GUILayout.Button("끝", GUILayout.Width(60))) StopMenu();
                }
                else
                {
                    GUILayout.Label("기록 안 함", EditorStyles.boldLabel);
                    GUILayout.FlexibleSpace();
                    if (GUILayout.Button("시작", GUILayout.Width(60))) ChangeRecorder.StartSession();
                }
            }

            if (ChangeRecorder.IsRecording)
                EditorGUILayout.LabelField(Path.GetFileName(ChangeRecorder.SessionDir), EditorStyles.miniLabel);

            EditorGUILayout.Space(6);
            using (new EditorGUI.DisabledScope(!ChangeRecorder.IsRecording))
            using (new EditorGUILayout.HorizontalScope())
            {
                GUI.SetNextControlName("marker");
                markerText = EditorGUILayout.TextField(markerText);
                bool enter = Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.Return
                             && GUI.GetNameOfFocusedControl() == "marker";
                if (GUILayout.Button("마커 (Ctrl+Shift+M)", GUILayout.Width(140)) || enter)
                {
                    ChangeRecorder.Marker(markerText.Trim());
                    markerText = "";
                    GUI.FocusControl(null);
                    if (enter) Event.current.Use();
                }
            }
            EditorGUILayout.LabelField("설명으로 들어가기 전, 학생을 멈추는 지점마다 마커를 찍는다. 글은 안 써도 된다.", EditorStyles.wordWrappedMiniLabel);

            EditorGUILayout.Space(6);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("폴더 열기")) OpenFolder();
                using (new EditorGUI.DisabledScope(string.IsNullOrEmpty(ChangeRecorder.LastSessionDir)))
                    if (GUILayout.Button("보고서 만들기")) BuildReport();
            }

            EditorGUILayout.Space(6);
            EditorGUILayout.LabelField("최근 사건", EditorStyles.boldLabel);
            using (var sv = new EditorGUILayout.ScrollViewScope(scroll))
            {
                scroll = sv.scrollPosition;
                var list = ChangeRecorder.Recent;
                for (int i = list.Count - 1; i >= 0; i--) EditorGUILayout.LabelField(list[i], mono);
                if (list.Count == 0) EditorGUILayout.LabelField("(없음)", EditorStyles.miniLabel);
            }
        }

        /// <summary>python tools/record-report.py 를 돌려 report.md 를 만든다. python 이 없으면 폴더 위치만 알려준다.</summary>
        static void BuildReport()
        {
            var dir = ChangeRecorder.IsRecording ? ChangeRecorder.SessionDir : ChangeRecorder.LastSessionDir;
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return;
            var script = ChangeRecorder.ProjectRoot + "/tools/record-report.py";
            if (!File.Exists(script))
            {
                EditorUtility.DisplayDialog("수업 기록", "tools/record-report.py 가 이 프로젝트에 없습니다.\n기록 폴더를 교재 프로젝트로 가져가서 보고서를 만드세요.\n\n" + dir, "확인");
                return;
            }
            // 파이썬을 세 이름으로 차례로 찾는다. python.org 설치본은 py 런처만 있을 수 있고,
            // 파이썬이 없는 윈도우는 "python" 이 Microsoft Store 안내문을 찍는 껍데기(종료코드 9009)다.
            string scriptArgs = "\"" + script + "\" \"" + dir + "\"";
            var candidates = new[] { new[] { "python", scriptArgs }, new[] { "py", "-3 " + scriptArgs }, new[] { "python3", scriptArgs } };
            string lastOut = "", lastErr = "";
            foreach (var c in candidates)
            {
                string outp, err; int code;
                if (!TryRunPython(c[0], c[1], out outp, out err, out code)) continue;   // 그 이름이 없다
                bool storeStub = code == 9009 || (outp + err).Contains("was not found") || (outp + err).Contains("Microsoft Store");
                if (storeStub) continue;
                if (code == 0 && File.Exists(dir + "/report.md"))
                {
                    EditorUtility.OpenWithDefaultApp(dir + "/report.md");
                    return;
                }
                EditorUtility.DisplayDialog("수업 기록", "보고서 생성 실패 (" + c[0] + ")\n\n" + outp + "\n" + err, "확인");
                return;
            }
            EditorUtility.DisplayDialog("수업 기록",
                "이 PC 에 파이썬이 없어서 보고서를 만들 수 없습니다.\n\n" +
                "설치: 시작 메뉴 → Microsoft Store → \"Python 3\" 검색 → 설치 (무료, 1~2분).\n" +
                "설치 후 이 버튼을 다시 누르면 됩니다. Unity 를 다시 켤 필요는 없습니다.\n\n" +
                "또는 아래 기록 폴더를 교재 프로젝트의 recordings/ 로 가져가서\n" +
                "python tools/record-report.py 를 실행하세요.\n\n" + dir,
                "확인");
            if (!string.IsNullOrEmpty(lastOut + lastErr)) UnityEngine.Debug.Log("[수업 기록] " + lastOut + lastErr);
        }

        /// <summary>exe 를 실행해 본다. 실행 파일 자체가 없으면 false. 있으면 출력과 종료코드를 돌려준다.</summary>
        static bool TryRunPython(string exe, string args, out string outp, out string err, out int code)
        {
            outp = ""; err = ""; code = -1;
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = exe,
                    Arguments = args,
                    WorkingDirectory = ChangeRecorder.ProjectRoot,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = System.Text.Encoding.UTF8,
                    StandardErrorEncoding = System.Text.Encoding.UTF8,
                };
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                using (var p = Process.Start(psi))
                {
                    err = p.StandardError.ReadToEnd();
                    outp = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(60000);
                    code = p.ExitCode;
                    return true;
                }
            }
            catch (System.ComponentModel.Win32Exception)
            {
                return false;   // 그 이름의 실행 파일이 없다
            }
        }
    }
}
