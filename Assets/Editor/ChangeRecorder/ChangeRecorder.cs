using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

#pragma warning disable 618   // InstanceIDToObject: 6000.3 에서 구식 표시됐지만 6000.0~6000.2 호환을 위해 그대로 쓴다

namespace ClassRecorder
{
    /// <summary>
    /// 수업 중 Unity 에디터와 코드가 어떻게 바뀌는지 시각과 함께 기록한다.
    ///
    ///   메뉴  기록 ▸ 시작 / 끝 / 마커(Ctrl+Shift+M) / 창 열기
    ///   결과  recordings/&lt;날짜_시각&gt;/events.jsonl   한 줄이 사건 하나 (시각·경과초·종류·내용)
    ///         recordings/&lt;날짜_시각&gt;/snapshots/      코드·씬·프리팹·머티리얼 사본 (저장될 때마다)
    ///   보고서  python tools/record-report.py          → report.md
    ///
    /// 잡는 것: 오브젝트 생성·삭제·부모변경, 컴포넌트 추가·제거, Inspector 값 변화(이전→이후),
    ///          머티리얼 값 변화, 에셋 생성·삭제·이동, 파일 저장(코드 diff 용 사본), 씬 저장,
    ///          프리팹 편집 모드, 선택(클릭), Play/Stop/Pause/Step, 컴파일과 에러, Console 로그, Undo.
    ///
    /// 이 폴더(Assets/Editor/ChangeRecorder)만 다른 프로젝트에 복사하면 그대로 돈다.
    /// 기록 상태는 EditorPrefs 에 두므로 스크립트 컴파일·Play 진입의 도메인 리로드를 넘긴다.
    /// </summary>
    [InitializeOnLoad]
    public static class ChangeRecorder
    {
        static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        static readonly Encoding Utf8 = new UTF8Encoding(false);

        // ───────────────────────── 경로 ─────────────────────────
        public static readonly string ProjectRoot = Path.GetDirectoryName(Application.dataPath).Replace('\\', '/');

        static string Rel(string full)
        {
            full = full.Replace('\\', '/');
            return full.StartsWith(ProjectRoot + "/", StringComparison.OrdinalIgnoreCase)
                ? full.Substring(ProjectRoot.Length + 1) : full;
        }

        // ───────────────────────── 상태 ─────────────────────────
        // EditorPrefs 키. 프로젝트마다 달라야 하므로 경로의 안정 해시를 붙인다 (string.GetHashCode 는 프로세스마다 달라질 수 있다).
        static readonly string K = "ClassRecorder." + StableHash(ProjectRoot) + ".";

        public static string SessionDir { get; private set; }
        public static DateTime StartTime { get; private set; }
        public static int Seq { get; private set; }
        public static int MarkerCount { get; private set; }
        public static bool IsRecording => SessionDir != null;
        public static string LastSessionDir => EditorPrefs.GetString(K + "lastdir", "");
        public static string EventsPath => SessionDir + "/events.jsonl";

        /// <summary>창에 보여줄 최근 사건 (짧은 문장). 도메인 리로드 때 비워진다.</summary>
        public static readonly List<string> Recent = new List<string>();
        public static event Action Changed;

        // AssetImportWorker 같은 배치 모드 Unity 프로세스도 에디터 스크립트를 로드한다.
        // 그쪽은 EditorPrefs 를 공유하므로 가만두면 같은 세션에 같이 써 버린다.
        static readonly bool Passive = Application.isBatchMode;

        static ChangeRecorder()
        {
            if (Passive) return;
            var dir = EditorPrefs.GetString(K + "dir", "");
            if (!string.IsNullOrEmpty(dir) && Directory.Exists(dir))
            {
                SessionDir = dir;
                StartTime = ParseIso(EditorPrefs.GetString(K + "start", ""), DateTime.Now);
                Seq = EditorPrefs.GetInt(K + "seq", 0);
                MarkerCount = EditorPrefs.GetInt(K + "markers", 0);
                snapSeq = EditorPrefs.GetInt(K + "snap", 0);
                playing = EditorApplication.isPlaying;

                var last = ParseIso(EditorPrefs.GetString(K + "last", ""), DateTime.Now);
                if ((DateTime.Now - last).TotalHours > 3)
                {
                    // 수업이 끝났는데 끝을 안 누른 채 며칠 뒤 다시 연 경우. 옛 세션에 덧쓰지 않는다.
                    WriteNow(DateTime.Now, "session_stop", new object[] { "reason", "auto: 3시간 이상 비어 있어 자동 종료" });
                    ClearState();
                }
                else
                {
                    LoadSnapshotIndex();
                    LoadKnownAssets();
                    Attach();
                    Log("reload");
                    needCache = true;   // 씬 접근은 에디터가 한 틱 돈 뒤에 (update 에서)
                }
            }
            AssemblyReloadEvents.beforeAssemblyReload += OnBeforeReload;
            EditorApplication.quitting += OnQuitting;
        }

        // ───────────────────────── 시작 / 끝 / 마커 ─────────────────────────
        public static void StartSession()
        {
            if (IsRecording || Passive) return;
            var stamp = DateTime.Now.ToString("yyyy-MM-dd_HHmm");
            var dir = ProjectRoot + "/recordings/" + stamp;
            for (int i = 2; Directory.Exists(dir); i++) dir = ProjectRoot + "/recordings/" + stamp + "-" + i;
            Directory.CreateDirectory(dir + "/snapshots");

            SessionDir = dir;
            StartTime = DateTime.Now;
            Seq = 0; MarkerCount = 0; snapSeq = 0;
            lastHash.Clear(); knownAssets.Clear(); goCache.Clear(); assetCache.Clear(); Recent.Clear();
            playing = EditorApplication.isPlaying;

            EditorPrefs.SetString(K + "dir", dir);
            EditorPrefs.SetString(K + "lastdir", dir);
            EditorPrefs.SetString(K + "start", StartTime.ToString("o"));
            EditorPrefs.SetInt(K + "seq", 0);
            EditorPrefs.SetInt(K + "markers", 0);
            EditorPrefs.SetInt(K + "snap", 0);

            Log("session_start",
                "project", Path.GetFileName(ProjectRoot),
                "unity", Application.unityVersion,
                "scene", SceneManager.GetActiveScene().path,
                "dir", Rel(dir));

            try { Baseline(); } catch (Exception e) { Log("error", "where", "baseline", "msg", e.Message); }
            try { InitKnownAssets(); } catch (Exception e) { Log("error", "where", "assets", "msg", e.Message); }
            BuildCaches();
            Attach();
            Drain();
            Changed?.Invoke();
        }

        public static void StopSession(string reason = "menu")
        {
            if (!IsRecording) return;
            FlushAll(DateTime.Now, force: true);
            FlushLogSummary();
            Log("session_stop", "reason", reason, "seconds", (DateTime.Now - StartTime).TotalSeconds);
            Drain();
            Detach();
            ClearState();
            Changed?.Invoke();
        }

        public static void Marker(string text)
        {
            if (!IsRecording) return;
            MarkerCount++;
            EditorPrefs.SetInt(K + "markers", MarkerCount);
            Log("marker", "n", MarkerCount, "text", text ?? "");
            Drain();
        }

        static void ClearState()
        {
            SessionDir = null;
            EditorPrefs.DeleteKey(K + "dir");
            EditorPrefs.DeleteKey(K + "start");
            EditorPrefs.DeleteKey(K + "seq");
            EditorPrefs.DeleteKey(K + "markers");
            EditorPrefs.DeleteKey(K + "snap");
            EditorPrefs.DeleteKey(K + "last");
            EditorPrefs.DeleteKey(K + "playstart");
        }

        static void OnBeforeReload()
        {
            if (!IsRecording) return;
            FlushAll(DateTime.Now, force: true);
            Drain();
            StopWatcher();
        }

        static void OnQuitting()
        {
            if (!IsRecording) return;
            FlushAll(DateTime.Now, force: true);
            Log("editor_quit");
            Drain();
            StopWatcher();
        }

        // ───────────────────────── 사건 쓰기 ─────────────────────────
        struct Pending { public DateTime t; public string kind; public object[] kv; }
        static readonly ConcurrentQueue<Pending> queue = new ConcurrentQueue<Pending>();

        /// <summary>어느 스레드에서든 호출 가능. 실제 쓰기는 메인 스레드의 update 에서 한다.</summary>
        public static void Log(string kind, params object[] kv) => LogAt(DateTime.Now, kind, kv);
        public static void LogAt(DateTime t, string kind, params object[] kv)
        {
            if (!IsRecording) return;
            queue.Enqueue(new Pending { t = t, kind = kind, kv = kv });
        }

        static void Drain()
        {
            while (queue.TryDequeue(out var p)) WriteNow(p.t, p.kind, p.kv);
        }

        static void WriteNow(DateTime t, string kind, object[] kv)
        {
            if (SessionDir == null) return;
            Seq++;
            var line = ToJson(t, Seq, kind, kv);
            try { File.AppendAllText(EventsPath, line + "\n", Utf8); }
            catch (Exception e) { Debug.LogWarning("[기록] 쓰기 실패: " + e.Message); }
            EditorPrefs.SetInt(K + "seq", Seq);
            EditorPrefs.SetString(K + "last", t.ToString("o"));
            Recent.Add(t.ToString("HH:mm:ss") + "  " + Short(kind, kv));
            if (Recent.Count > 60) Recent.RemoveAt(0);
            Changed?.Invoke();
        }

        static string ToJson(DateTime t, int n, string kind, object[] kv)
        {
            var sb = new StringBuilder(256);
            sb.Append("{\"t\":\"").Append(t.ToString("yyyy-MM-dd'T'HH:mm:ss.fff")).Append('"');
            sb.Append(",\"e\":").Append((t - StartTime).TotalSeconds.ToString("0.0", Inv));
            sb.Append(",\"n\":").Append(n);
            sb.Append(",\"kind\":\"").Append(Esc(kind)).Append('"');
            if (kv != null)
                for (int i = 0; i + 1 < kv.Length; i += 2)
                {
                    sb.Append(",\"").Append(Esc(kv[i] as string ?? "?")).Append("\":");
                    AppendValue(sb, kv[i + 1]);
                }
            sb.Append('}');
            return sb.ToString();
        }

        static void AppendValue(StringBuilder sb, object v)
        {
            switch (v)
            {
                case null: sb.Append("null"); break;
                case string s: sb.Append('"').Append(Esc(s)).Append('"'); break;
                case bool b: sb.Append(b ? "true" : "false"); break;
                case int i: sb.Append(i); break;
                case long l: sb.Append(l); break;
                case float f: sb.Append(f.ToString("0.###", Inv)); break;
                case double d: sb.Append(d.ToString("0.###", Inv)); break;
                case IEnumerable<string> list:
                    sb.Append('[');
                    bool first = true;
                    foreach (var s in list) { if (!first) sb.Append(','); first = false; sb.Append('"').Append(Esc(s)).Append('"'); }
                    sb.Append(']');
                    break;
                default: sb.Append('"').Append(Esc(v.ToString())).Append('"'); break;
            }
        }

        static string Esc(string s)
        {
            if (s == null) return "";
            var sb = new StringBuilder(s.Length + 8);
            foreach (var c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }

        /// <summary>창에 보여줄 한 줄 요약.</summary>
        static string Short(string kind, object[] kv)
        {
            string G(string key)
            {
                if (kv == null) return "";
                for (int i = 0; i + 1 < kv.Length; i += 2)
                    if ((kv[i] as string) == key)
                        return kv[i + 1] == null ? "" : (kv[i + 1] is IEnumerable<string> l ? string.Join(", ", l) : kv[i + 1].ToString());
                return "";
            }
            switch (kind)
            {
                case "marker": return "■ 마커 " + G("n") + "  " + G("text");
                case "select": return "선택  " + (G("obj") != "" ? G("obj") : G("asset"));
                case "go_create": return "생성  " + G("obj") + "  [" + G("comps") + "]";
                case "go_destroy": return "삭제  " + G("obj");
                case "go_parent": return "부모  " + G("obj") + ": " + G("from") + " → " + G("to");
                case "comp_add": return "컴포넌트 +  " + G("comp") + "  @ " + G("obj");
                case "comp_remove": return "컴포넌트 −  " + G("comp") + "  @ " + G("obj");
                case "prop": return "값  " + G("obj") + " · " + G("comp") + " · " + G("path") + ": " + G("from") + " → " + G("to");
                case "asset_prop": return "값  " + G("asset") + " · " + G("path") + ": " + G("from") + " → " + G("to");
                case "touch": return "변경  " + G("obj") + G("asset") + " (세부 불명)";
                case "asset_create": return "에셋 생성  " + G("asset");
                case "asset_delete": return "에셋 삭제  " + G("asset");
                case "asset_move": return "에셋 이동  " + G("from") + " → " + G("asset");
                case "asset_import": return "에셋 변경  " + G("asset");
                case "file": return "저장  " + G("path") + "  (" + G("lines") + "줄)";
                case "scene_save": return "씬 저장  " + G("scene");
                case "scene_open": return "씬 열기  " + G("scene");
                case "prefab_stage": return "프리팹 편집 " + G("state") + "  " + G("asset");
                case "play": return "Play " + G("state") + (G("seconds") != "" ? "  " + G("seconds") + "초" : "") + (G("frame") != "" ? "  frame " + G("frame") : "");
                case "compile": return "컴파일 " + G("state") + (G("errors") != "" ? "  에러: " + G("errors") : "");
                case "log": return "Console " + G("type") + "  " + G("msg");
                case "log_summary": return "Console 반복  " + G("items");
                case "undo": return (G("redo") == "True" ? "다시 실행  " : "되돌리기  ") + G("name");
                case "children_order": return "순서 변경  " + G("obj");
                case "prefab_update": return "프리팹 인스턴스 갱신 ×" + G("count");
                case "play_summary": return "Play 중 생성/삭제  " + G("items");
                default: return kind + "  " + G("reason") + G("msg");
            }
        }

        // ───────────────────────── 훅 붙이기 ─────────────────────────
        static bool attached;

        static void Attach()
        {
            if (attached) return;
            attached = true;
            ObjectChangeEvents.changesPublished += OnObjectChanges;
            EditorApplication.hierarchyChanged += OnHierarchyChanged;
            Selection.selectionChanged += OnSelection;
            EditorApplication.playModeStateChanged += OnPlayMode;
            EditorApplication.pauseStateChanged += OnPause;
            CompilationPipeline.compilationStarted += OnCompileStart;
            CompilationPipeline.compilationFinished += OnCompileEnd;
            CompilationPipeline.assemblyCompilationFinished += OnAssemblyCompiled;
            EditorSceneManager.sceneSaved += OnSceneSaved;
            EditorSceneManager.sceneOpened += OnSceneOpened;
            EditorSceneManager.newSceneCreated += OnNewScene;
            PrefabStage.prefabStageOpened += OnPrefabOpened;
            PrefabStage.prefabStageClosing += OnPrefabClosing;
            Application.logMessageReceivedThreaded += OnLogMessage;
            Undo.undoRedoEvent += OnUndoRedo;
            EditorApplication.update += OnUpdate;
            StartWatcher();
        }

        static void Detach()
        {
            if (!attached) return;
            attached = false;
            ObjectChangeEvents.changesPublished -= OnObjectChanges;
            EditorApplication.hierarchyChanged -= OnHierarchyChanged;
            Selection.selectionChanged -= OnSelection;
            EditorApplication.playModeStateChanged -= OnPlayMode;
            EditorApplication.pauseStateChanged -= OnPause;
            CompilationPipeline.compilationStarted -= OnCompileStart;
            CompilationPipeline.compilationFinished -= OnCompileEnd;
            CompilationPipeline.assemblyCompilationFinished -= OnAssemblyCompiled;
            EditorSceneManager.sceneSaved -= OnSceneSaved;
            EditorSceneManager.sceneOpened -= OnSceneOpened;
            EditorSceneManager.newSceneCreated -= OnNewScene;
            PrefabStage.prefabStageOpened -= OnPrefabOpened;
            PrefabStage.prefabStageClosing -= OnPrefabClosing;
            Application.logMessageReceivedThreaded -= OnLogMessage;
            Undo.undoRedoEvent -= OnUndoRedo;
            EditorApplication.update -= OnUpdate;
            StopWatcher();
        }

        static bool needCache;

        static void OnUpdate()
        {
            if (!IsRecording) return;
            var now = DateTime.Now;
            try
            {
                if (needCache) { needCache = false; BuildCaches(); }
                FlushAll(now, force: false);
                DetectStep();
            }
            catch (Exception e) { Log("error", "where", "update", "msg", e.Message); }
            Drain();
        }

        static void FlushAll(DateTime now, bool force)
        {
            Reconcile(now);
            FlushTouches(now, force);
            FlushAssetTouches(now, force);
            FlushDirtyFiles(now, force);
        }

        // ───────────────────────── 오브젝트 캐시 ─────────────────────────
        // "이전 값 → 새 값" 을 내려면 바뀌기 전 상태를 알아야 한다. 씬의 오브젝트와 컴포넌트의
        // 직렬화된 값을 전부 들고 있다가, 바뀌었다는 신호가 오면 다시 읽어 비교한다.
        class GoInfo
        {
            public string path;
            public List<string> comps = new List<string>();
            public Dictionary<int, Dictionary<string, string>> props = new Dictionary<int, Dictionary<string, string>>();
        }

        static readonly Dictionary<int, GoInfo> goCache = new Dictionary<int, GoInfo>();
        static readonly Dictionary<int, Dictionary<string, string>> assetCache = new Dictionary<int, Dictionary<string, string>>();

        static bool cacheReady;
        static bool hierarchyDirty;
        static DateTime lastReconcile;

        static void OnHierarchyChanged() { hierarchyDirty = true; }

        /// <summary>
        /// 생성·삭제의 안전망. ObjectChangeEvents 는 Undo 를 거치지 않은 생성(도구·스크립트)을 놓친다.
        /// Hierarchy 가 바뀌었다는 신호가 오면 씬 전체를 캐시와 대조해 새로 생긴 것과 사라진 것을 적는다.
        /// </summary>
        static void Reconcile(DateTime now)
        {
            if (!cacheReady) return;
            // 신호(hierarchyChanged)가 왔을 때 + 신호와 무관하게 2초마다. 에디터가 프레임을 안 그리는 동안은
            // 변경 이벤트가 미뤄질 수 있어서, 주기 대조가 생성·삭제의 최종 안전망이다. 교실 규모 씬에선 비용이 없다.
            bool due = (now - lastReconcile).TotalSeconds >= 2;
            if (!hierarchyDirty && !due) return;
            if (playing && !due) return;   // Play 중엔 Instantiate 가 쏟아지므로 2초 단위로만
            hierarchyDirty = false; lastReconcile = now;

            var seen = new HashSet<int>();
            void Visit(GameObject root)
            {
                foreach (var t in root.GetComponentsInChildren<Transform>(true))
                {
                    var g = t.gameObject; int id = g.GetInstanceID();
                    seen.Add(id);
                    if (goCache.TryGetValue(id, out var cached))
                    {
                        // 컴포넌트 목록도 대조한다 — Play 진입 직전의 Add Component 처럼 이벤트가 미뤄진 경우의 안전망
                        if (playing) continue;
                        var comps = g.GetComponents<Component>();
                        if (comps.Length == cached.comps.Count)
                        {
                            bool same = true;
                            for (int c = 0; c < comps.Length; c++)
                                if ((comps[c] == null ? "Missing Script" : comps[c].GetType().Name) != cached.comps[c]) { same = false; break; }
                            if (same) continue;
                        }
                        var removed = new List<string>(cached.comps);
                        var added = new List<string>();
                        foreach (var c in comps) { var n = c == null ? "Missing Script" : c.GetType().Name; if (!removed.Remove(n)) added.Add(n); }
                        var fresh = CacheGo(g);
                        foreach (var c in added) LogAt(now, "comp_add", "obj", fresh.path, "comp", c);
                        foreach (var c in removed) LogAt(now, "comp_remove", "obj", fresh.path, "comp", c);
                        continue;
                    }
                    var info = CacheGo(g);
                    if (playing) Count(playCreated, g.name);
                    else LogAt(now, "go_create", "obj", info.path, "comps", info.comps);
                }
            }
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                var sc = SceneManager.GetSceneAt(i);
                if (!sc.isLoaded) continue;
                foreach (var root in sc.GetRootGameObjects()) Visit(root);
            }
            var stage = PrefabStageUtility.GetCurrentPrefabStage();
            if (stage != null && stage.prefabContentsRoot != null) Visit(stage.prefabContentsRoot);

            foreach (var id in goCache.Keys.ToList())
            {
                if (seen.Contains(id)) continue;
                var path = goCache[id].path;
                goCache.Remove(id); touchPending.Remove(id);
                if (playing) Count(playDestroyed, path); else LogAt(now, "go_destroy", "obj", path);
            }
        }

        static void BuildCaches()
        {
            if (!IsRecording) return;
            cacheReady = false;
            try
            {
                goCache.Clear();
                for (int i = 0; i < SceneManager.sceneCount; i++)
                {
                    var sc = SceneManager.GetSceneAt(i);
                    if (!sc.isLoaded) continue;
                    foreach (var root in sc.GetRootGameObjects())
                        foreach (var t in root.GetComponentsInChildren<Transform>(true))
                            CacheGo(t.gameObject);
                }
                var stage = PrefabStageUtility.GetCurrentPrefabStage();
                if (stage != null && stage.prefabContentsRoot != null)
                    foreach (var t in stage.prefabContentsRoot.GetComponentsInChildren<Transform>(true))
                        CacheGo(t.gameObject);

                assetCache.Clear();
                int n = 0;
                foreach (var guid in AssetDatabase.FindAssets("t:Material", new[] { "Assets" }))
                {
                    if (++n > 300) break;
                    var m = AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(guid));
                    if (m != null) assetCache[m.GetInstanceID()] = ReadAsset(m);
                }
            }
            catch (Exception e) { Log("error", "where", "cache", "msg", e.Message); }
            cacheReady = true;
            hierarchyDirty = false;
        }

        static GoInfo CacheGo(GameObject go)
        {
            if (go == null) return null;
            var info = new GoInfo { path = PathOf(go) };
            info.props[go.GetInstanceID()] = ReadProps(go);
            foreach (var c in go.GetComponents<Component>())
            {
                if (c == null) { info.comps.Add("Missing Script"); continue; }
                info.comps.Add(c.GetType().Name);
                info.props[c.GetInstanceID()] = ReadProps(c);
            }
            goCache[go.GetInstanceID()] = info;
            return info;
        }

        static void CacheSubtree(GameObject go)
        {
            if (go == null) return;
            foreach (var t in go.GetComponentsInChildren<Transform>(true)) CacheGo(t.gameObject);
        }

        static void RefreshPaths(GameObject go)
        {
            if (go == null) return;
            foreach (var t in go.GetComponentsInChildren<Transform>(true))
                if (goCache.TryGetValue(t.gameObject.GetInstanceID(), out var info)) info.path = PathOf(t.gameObject);
        }

        static string PathOf(GameObject go)
        {
            if (go == null) return "?";
            var sb = new StringBuilder(go.name);
            var t = go.transform.parent;
            while (t != null) { sb.Insert(0, t.name + "/"); t = t.parent; }
            var stage = PrefabStageUtility.GetCurrentPrefabStage();
            if (stage != null && go.scene == stage.scene)
                sb.Insert(0, "[프리팹 " + Path.GetFileNameWithoutExtension(stage.assetPath) + "] ");
            return sb.ToString();
        }

        static string NameOf(int instanceId)
        {
            if (goCache.TryGetValue(instanceId, out var info)) return info.path;
            var o = EditorUtility.InstanceIDToObject(instanceId);
            if (o is GameObject g) return PathOf(g);
            if (o is Component c) return PathOf(c.gameObject);
            return o != null ? o.name : "?";
        }

        // 직렬화된 값 읽기 — Inspector 에 보이는 것과 같은 단위로
        static readonly HashSet<string> SkipProps = new HashSet<string>
        {
            "m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance", "m_PrefabAsset",
            "m_GameObject", "m_EditorHideFlags", "m_EditorClassIdentifier", "m_Children", "m_Father",
            "m_RootOrder", "m_LocalEulerAnglesHint", "m_Component", "m_Icon", "m_NavMeshLayer",
            "m_StaticEditorFlags", "m_ConstrainProportionsScale",
        };

        static Dictionary<string, string> ReadProps(Object o)
        {
            var d = new Dictionary<string, string>();
            if (o == null) return d;
            try
            {
                using (var so = new SerializedObject(o))
                {
                    var p = so.GetIterator();
                    bool enter = true;
                    while (p.Next(enter))
                    {
                        enter = true;
                        if (p.depth == 0 && SkipProps.Contains(p.name)) { enter = false; continue; }
                        if (p.depth > 5) { enter = false; continue; }
                        if (p.propertyType == SerializedPropertyType.Generic)
                        {
                            if (p.isArray) d[p.propertyPath + " 개수"] = p.arraySize.ToString();
                            continue; // 자식으로 들어간다
                        }
                        d[p.propertyPath] = ValueOf(p);
                        enter = false;
                    }
                }
            }
            catch { }
            return d;
        }

        static string F(double v) => ((float)v).ToString("0.####", Inv);
        static string V(Vector2 v) => "(" + F(v.x) + ", " + F(v.y) + ")";
        static string V(Vector3 v) => "(" + F(v.x) + ", " + F(v.y) + ", " + F(v.z) + ")";
        static string V(Vector4 v) => "(" + F(v.x) + ", " + F(v.y) + ", " + F(v.z) + ", " + F(v.w) + ")";
        static string C(Color c) => "(" + F(c.r) + ", " + F(c.g) + ", " + F(c.b) + ", " + F(c.a) + ")";

        static string ValueOf(SerializedProperty p)
        {
            try
            {
                switch (p.propertyType)
                {
                    case SerializedPropertyType.Integer: return p.longValue.ToString(Inv);
                    case SerializedPropertyType.Boolean: return p.boolValue ? "true" : "false";
                    case SerializedPropertyType.Float: return F(p.doubleValue);
                    case SerializedPropertyType.String: return p.stringValue;
                    case SerializedPropertyType.Color: return C(p.colorValue);
                    case SerializedPropertyType.ObjectReference:
                        { var r = p.objectReferenceValue; return r == null ? "None" : r.name + " (" + r.GetType().Name + ")"; }
                    case SerializedPropertyType.LayerMask: return p.intValue.ToString(Inv);
                    case SerializedPropertyType.Enum:
                        {
                            var names = p.enumDisplayNames; var i = p.enumValueIndex;
                            return (names != null && i >= 0 && i < names.Length) ? names[i] : p.intValue.ToString(Inv);
                        }
                    case SerializedPropertyType.Vector2: return V(p.vector2Value);
                    case SerializedPropertyType.Vector3: return V(p.vector3Value);
                    case SerializedPropertyType.Vector4: return V(p.vector4Value);
                    case SerializedPropertyType.Rect: { var r = p.rectValue; return "(" + F(r.x) + ", " + F(r.y) + ", " + F(r.width) + ", " + F(r.height) + ")"; }
                    case SerializedPropertyType.ArraySize: return p.intValue.ToString(Inv);
                    case SerializedPropertyType.Character: return ((char)p.intValue).ToString();
                    case SerializedPropertyType.AnimationCurve: return "(curve)";
                    case SerializedPropertyType.Bounds: { var b = p.boundsValue; return "center " + V(b.center) + " size " + V(b.size); }
                    case SerializedPropertyType.Gradient: return "(gradient)";
                    case SerializedPropertyType.Quaternion: return V(p.quaternionValue.eulerAngles);
                    case SerializedPropertyType.ExposedReference: { var r = p.exposedReferenceValue; return r == null ? "None" : r.name; }
                    case SerializedPropertyType.FixedBufferSize: return p.intValue.ToString(Inv);
                    case SerializedPropertyType.Vector2Int: { var v = p.vector2IntValue; return "(" + v.x + ", " + v.y + ")"; }
                    case SerializedPropertyType.Vector3Int: { var v = p.vector3IntValue; return "(" + v.x + ", " + v.y + ", " + v.z + ")"; }
                    case SerializedPropertyType.RectInt: { var r = p.rectIntValue; return "(" + r.x + ", " + r.y + ", " + r.width + ", " + r.height + ")"; }
                    case SerializedPropertyType.BoundsInt: return "(bounds)";
                    case SerializedPropertyType.ManagedReference: return "(managed)";
                    case SerializedPropertyType.Hash128: return p.hash128Value.ToString();
                    default: return "?";
                }
            }
            catch { return "?"; }
        }

        static Dictionary<string, string> ReadAsset(Object o)
        {
            if (o is Material m) return ReadMaterial(m);
            return ReadProps(o);
        }

        static Dictionary<string, string> ReadMaterial(Material m)
        {
            var d = new Dictionary<string, string>();
            try
            {
                var sh = m.shader;
                d["Shader"] = sh != null ? sh.name : "None";
                int n = sh != null ? sh.GetPropertyCount() : 0;
                for (int i = 0; i < n; i++)
                {
                    var name = sh.GetPropertyName(i);
                    switch (sh.GetPropertyType(i))
                    {
                        case UnityEngine.Rendering.ShaderPropertyType.Color: d[name] = C(m.GetColor(name)); break;
                        case UnityEngine.Rendering.ShaderPropertyType.Vector: d[name] = V(m.GetVector(name)); break;
                        case UnityEngine.Rendering.ShaderPropertyType.Float:
                        case UnityEngine.Rendering.ShaderPropertyType.Range: d[name] = F(m.GetFloat(name)); break;
                        case UnityEngine.Rendering.ShaderPropertyType.Int: d[name] = m.GetInteger(name).ToString(Inv); break;
                        case UnityEngine.Rendering.ShaderPropertyType.Texture: { var t = m.GetTexture(name); d[name] = t != null ? t.name : "None"; break; }
                    }
                }
                d["RenderQueue"] = m.renderQueue.ToString(Inv);
            }
            catch { }
            return d;
        }

        static int DiffProps(Dictionary<string, string> before, Dictionary<string, string> after, Action<string, string, string> emit)
        {
            int n = 0;
            foreach (var kv in after)
            {
                string old;
                if (!before.TryGetValue(kv.Key, out old)) old = "(없음)";
                if (old == kv.Value) continue;
                emit(kv.Key, old, kv.Value);
                n++;
            }
            return n;
        }

        // ───────────────────────── ObjectChangeEvents ─────────────────────────
        static readonly Dictionary<int, DateTime[]> touchPending = new Dictionary<int, DateTime[]>();      // goId → [first, last]
        static readonly Dictionary<int, object[]> assetTouchPending = new Dictionary<int, object[]>();      // instanceId → [first, last, assetPath]
        static readonly Dictionary<string, int> playCreated = new Dictionary<string, int>();
        static readonly Dictionary<string, int> playDestroyed = new Dictionary<string, int>();

        static void OnObjectChanges(ref ObjectChangeEventStream stream)
        {
            if (!IsRecording) return;
            var now = DateTime.Now;
            for (int i = 0; i < stream.length; i++)
            {
                try
                {
                    switch (stream.GetEventType(i))
                    {
                        case ObjectChangeKind.CreateGameObjectHierarchy:
                            {
                                stream.GetCreateGameObjectHierarchyEvent(i, out var e);
                                var go = EditorUtility.InstanceIDToObject(e.instanceId) as GameObject;
                                if (go == null) break;
                                var info = CacheGo(go);
                                var all = go.GetComponentsInChildren<Transform>(true);
                                foreach (var t in all) if (t.gameObject != go) CacheGo(t.gameObject);
                                if (playing) { Count(playCreated, go.name); break; }
                                int children = all.Length - 1;
                                if (children > 0) LogAt(now, "go_create", "obj", info.path, "comps", info.comps, "children", children);
                                else LogAt(now, "go_create", "obj", info.path, "comps", info.comps);
                                break;
                            }
                        case ObjectChangeKind.DestroyGameObjectHierarchy:
                            {
                                stream.GetDestroyGameObjectHierarchyEvent(i, out var e);
                                string path = goCache.TryGetValue(e.instanceId, out var info) ? info.path : "?";
                                if (playing) Count(playDestroyed, path); else LogAt(now, "go_destroy", "obj", path);
                                goCache.Remove(e.instanceId);
                                touchPending.Remove(e.instanceId);
                                if (path != "?")
                                    foreach (var k in goCache.Where(kv => kv.Value.path.StartsWith(path + "/")).Select(kv => kv.Key).ToList())
                                        goCache.Remove(k);
                                break;
                            }
                        case ObjectChangeKind.ChangeGameObjectStructure:
                            {
                                stream.GetChangeGameObjectStructureEvent(i, out var e);
                                StructureChanged(now, EditorUtility.InstanceIDToObject(e.instanceId) as GameObject, false);
                                break;
                            }
                        case ObjectChangeKind.ChangeGameObjectStructureHierarchy:
                            {
                                stream.GetChangeGameObjectStructureHierarchyEvent(i, out var e);
                                StructureChanged(now, EditorUtility.InstanceIDToObject(e.instanceId) as GameObject, true);
                                break;
                            }
                        case ObjectChangeKind.ChangeGameObjectParent:
                            {
                                stream.GetChangeGameObjectParentEvent(i, out var e);
                                var go = EditorUtility.InstanceIDToObject(e.instanceId) as GameObject;
                                string from = e.previousParentInstanceId == 0 ? "(루트)" : NameOf(e.previousParentInstanceId);
                                string to = e.newParentInstanceId == 0 ? "(루트)" : NameOf(e.newParentInstanceId);
                                LogAt(now, "go_parent", "obj", go != null ? go.name : NameOf(e.instanceId), "from", from, "to", to);
                                RefreshPaths(go);
                                break;
                            }
                        case ObjectChangeKind.ChangeGameObjectOrComponentProperties:
                            {
                                stream.GetChangeGameObjectOrComponentPropertiesEvent(i, out var e);
                                var o = EditorUtility.InstanceIDToObject(e.instanceId);
                                int goId = o is Component c ? c.gameObject.GetInstanceID() : (o is GameObject g ? g.GetInstanceID() : 0);
                                if (goId == 0) break;
                                if (touchPending.TryGetValue(goId, out var span)) span[1] = now;
                                else touchPending[goId] = new[] { now, now };
                                break;
                            }
                        case ObjectChangeKind.CreateAssetObject:
                            {
                                stream.GetCreateAssetObjectEvent(i, out var e);
                                var o = EditorUtility.InstanceIDToObject(e.instanceId);
                                if (o != null) assetCache[e.instanceId] = ReadAsset(o);
                                break;
                            }
                        case ObjectChangeKind.DestroyAssetObject:
                            {
                                stream.GetDestroyAssetObjectEvent(i, out var e);
                                assetCache.Remove(e.instanceId);
                                assetTouchPending.Remove(e.instanceId);
                                break;
                            }
                        case ObjectChangeKind.ChangeAssetObjectProperties:
                            {
                                stream.GetChangeAssetObjectPropertiesEvent(i, out var e);
                                var path = AssetDatabase.GUIDToAssetPath(e.guid);
                                if (assetTouchPending.TryGetValue(e.instanceId, out var span)) span[1] = now;
                                else assetTouchPending[e.instanceId] = new object[] { now, now, path };
                                break;
                            }
                        case ObjectChangeKind.UpdatePrefabInstances:
                            {
                                stream.GetUpdatePrefabInstancesEvent(i, out var e);
                                LogAt(now, "prefab_update", "count", e.instanceIds.Length);
                                foreach (var id in e.instanceIds)
                                    if (EditorUtility.InstanceIDToObject(id) is GameObject g) CacheSubtree(g);
                                break;
                            }
                        case ObjectChangeKind.ChangeChildrenOrder:
                            {
                                stream.GetChangeChildrenOrderEvent(i, out var e);
                                LogAt(now, "children_order", "obj", NameOf(e.instanceId));
                                break;
                            }
                        default: break;  // ChangeScene 은 더티 표시 변화라 소음이다
                    }
                }
                catch (Exception ex) { LogAt(now, "error", "where", "objectchange", "msg", ex.Message); }
            }
        }

        static void Count(Dictionary<string, int> d, string key)
        {
            d.TryGetValue(key, out var n); d[key] = n + 1;
        }

        static void StructureChanged(DateTime now, GameObject go, bool hierarchy)
        {
            if (go == null) return;
            var targets = hierarchy ? go.GetComponentsInChildren<Transform>(true).Select(t => t.gameObject).ToArray() : new[] { go };
            foreach (var g in targets)
            {
                int id = g.GetInstanceID();
                goCache.TryGetValue(id, out var before);
                var after = CacheGo(g);
                if (before == null) continue;
                var removed = new List<string>(before.comps);
                var added = new List<string>();
                foreach (var c in after.comps) { if (!removed.Remove(c)) added.Add(c); }
                foreach (var c in added) LogAt(now, "comp_add", "obj", after.path, "comp", c);
                foreach (var c in removed) LogAt(now, "comp_remove", "obj", after.path, "comp", c);
            }
        }

        // 연속된 변화(슬라이더 드래그 등)는 0.5초 조용해진 뒤 한 번에 "처음 → 마지막" 으로 적는다
        static void FlushTouches(DateTime now, bool force)
        {
            if (touchPending.Count == 0) return;
            var done = new List<int>();
            foreach (var kv in touchPending)
            {
                if (!force && (now - kv.Value[1]).TotalSeconds < 0.5) continue;
                done.Add(kv.Key);
                var go = EditorUtility.InstanceIDToObject(kv.Key) as GameObject;
                if (go == null) continue;
                var first = kv.Value[0];
                if (!goCache.TryGetValue(kv.Key, out var before)) { var fresh = CacheGo(go); LogAt(first, "touch", "obj", fresh.path); continue; }
                var after = CacheGo(go);
                int n = 0;
                string renamedTo = null;

                // 컴포넌트 목록 차이 — Inspector 의 Add Component 가 구조 이벤트 없이 올 때를 위해
                var removedComps = new List<string>(before.comps);
                var addedComps = new List<string>();
                foreach (var c in after.comps) { if (!removedComps.Remove(c)) addedComps.Add(c); }
                foreach (var c in addedComps) LogAt(first, "comp_add", "obj", before.path, "comp", c);
                foreach (var c in removedComps) LogAt(first, "comp_remove", "obj", before.path, "comp", c);
                n += addedComps.Count + removedComps.Count;

                foreach (var pair in after.props)
                {
                    Dictionary<string, string> old;
                    if (!before.props.TryGetValue(pair.Key, out old)) continue;   // 방금 추가된 컴포넌트: comp_add 로 충분
                    var target = EditorUtility.InstanceIDToObject(pair.Key);
                    string comp = target is GameObject ? "GameObject" : (target != null ? target.GetType().Name : "?");
                    n += DiffProps(old, pair.Value, (path, from, to) =>
                    {
                        if (comp == "GameObject" && path == "m_Name") renamedTo = to;
                        LogAt(first, "prop", "obj", before.path, "comp", comp, "path", path, "from", from, "to", to);
                    });
                }
                if (n == 0) LogAt(first, "touch", "obj", before.path);
                if (renamedTo != null) RefreshPaths(go);
            }
            foreach (var k in done) touchPending.Remove(k);
        }

        static void FlushAssetTouches(DateTime now, bool force)
        {
            if (assetTouchPending.Count == 0) return;
            var done = new List<int>();
            foreach (var kv in assetTouchPending)
            {
                var first = (DateTime)kv.Value[0]; var last = (DateTime)kv.Value[1]; var path = (string)kv.Value[2];
                if (!force && (now - last).TotalSeconds < 0.5) continue;
                done.Add(kv.Key);
                var o = EditorUtility.InstanceIDToObject(kv.Key);
                if (o == null) continue;
                var after = ReadAsset(o);
                string label = string.IsNullOrEmpty(path) ? o.name : path;
                if (!string.IsNullOrEmpty(path) && o.name != Path.GetFileNameWithoutExtension(path)) label += " · " + o.name;
                if (!assetCache.TryGetValue(kv.Key, out var before)) { assetCache[kv.Key] = after; LogAt(first, "touch", "asset", label); continue; }
                assetCache[kv.Key] = after;
                int n = DiffProps(before, after, (p, from, to) => LogAt(first, "asset_prop", "asset", label, "type", o.GetType().Name, "path", p, "from", from, "to", to));
                if (n == 0) LogAt(first, "touch", "asset", label);
            }
            foreach (var k in done) assetTouchPending.Remove(k);
        }

        // ───────────────────────── 선택 / Undo / 씬 / 프리팹 ─────────────────────────
        static void OnSelection()
        {
            if (!IsRecording) return;
            var objs = Selection.objects;
            if (objs == null || objs.Length == 0) return;
            var o = Selection.activeObject;
            if (o is GameObject g)
            {
                if (objs.Length > 1) Log("select", "obj", PathOf(g), "count", objs.Length);
                else Log("select", "obj", PathOf(g));
            }
            else if (o != null)
            {
                var p = AssetDatabase.GetAssetPath(o);
                Log("select", "asset", string.IsNullOrEmpty(p) ? o.name + " (" + o.GetType().Name + ")" : p);
            }
        }

        static void OnUndoRedo(in UndoRedoInfo info)
        {
            Log("undo", "name", info.undoName, "redo", info.isRedo);
        }

        static void OnSceneSaved(Scene s) => Log("scene_save", "scene", s.path);
        static void OnSceneOpened(Scene s, OpenSceneMode m) { Log("scene_open", "scene", s.path, "mode", m.ToString()); needCache = true; }
        static void OnNewScene(Scene s, NewSceneSetup setup, NewSceneMode m) { Log("scene_new", "scene", s.path); needCache = true; }
        static void OnPrefabOpened(PrefabStage st)
        {
            Log("prefab_stage", "state", "open", "asset", st.assetPath);
            if (st.prefabContentsRoot != null) CacheSubtree(st.prefabContentsRoot);
        }
        static void OnPrefabClosing(PrefabStage st) => Log("prefab_stage", "state", "close", "asset", st.assetPath);

        // ───────────────────────── Play / Pause / Step ─────────────────────────
        static bool playing;
        static int lastFrame = -1;

        static void OnPlayMode(PlayModeStateChange s)
        {
            switch (s)
            {
                case PlayModeStateChange.EnteredPlayMode:
                    playing = true;
                    EditorPrefs.SetString(K + "playstart", DateTime.Now.ToString("o"));
                    lock (logLock) logCounts.Clear();
                    playCreated.Clear(); playDestroyed.Clear();
                    Log("play", "state", "start");
                    needCache = true;
                    break;
                case PlayModeStateChange.ExitingPlayMode:
                    {
                        FlushAll(DateTime.Now, force: true);
                        FlushLogSummary();
                        var start = ParseIso(EditorPrefs.GetString(K + "playstart", ""), DateTime.Now);
                        var items = new List<string>();
                        foreach (var kv in playCreated) items.Add("생성 " + kv.Key + " ×" + kv.Value);
                        foreach (var kv in playDestroyed) items.Add("삭제 " + kv.Key + " ×" + kv.Value);
                        if (items.Count > 0) Log("play_summary", "items", items);
                        Log("play", "state", "stop", "seconds", (DateTime.Now - start).TotalSeconds);
                        playing = false;
                        playCreated.Clear(); playDestroyed.Clear();
                        break;
                    }
                case PlayModeStateChange.EnteredEditMode:
                    playing = false;
                    needCache = true;
                    break;
            }
        }

        static void OnPause(PauseState st)
        {
            if (!EditorApplication.isPlaying) return;
            Log("play", "state", st == PauseState.Paused ? "pause" : "unpause", "frame", Time.frameCount);
        }

        static void DetectStep()
        {
            if (!EditorApplication.isPlaying) { lastFrame = -1; return; }
            int f = Time.frameCount;
            if (EditorApplication.isPaused)
            {
                if (lastFrame >= 0 && f != lastFrame) Log("play", "state", "step", "frame", f);
            }
            lastFrame = f;
        }

        // ───────────────────────── 컴파일 ─────────────────────────
        static DateTime compileStart;
        static readonly List<string> compileErrors = new List<string>();
        static int compileWarnings;

        static void OnCompileStart(object o)
        {
            compileStart = DateTime.Now; compileErrors.Clear(); compileWarnings = 0;
            Log("compile", "state", "start");
        }

        static void OnAssemblyCompiled(string asm, CompilerMessage[] msgs)
        {
            foreach (var m in msgs)
            {
                if (m.type == CompilerMessageType.Error) compileErrors.Add(Rel(m.file) + ":" + m.line + "  " + m.message);
                else if (m.type == CompilerMessageType.Warning) compileWarnings++;
            }
        }

        static void OnCompileEnd(object o)
        {
            var secs = (DateTime.Now - compileStart).TotalSeconds;
            if (compileErrors.Count > 0) Log("compile", "state", "end", "seconds", secs, "errors", compileErrors.ToList(), "warnings", compileWarnings);
            else Log("compile", "state", "end", "seconds", secs, "warnings", compileWarnings);
            Drain();
        }

        // ───────────────────────── Console ─────────────────────────
        static readonly object logLock = new object();
        static readonly Dictionary<string, int> logCounts = new Dictionary<string, int>();
        static readonly string[] IgnoreLogs = { "[기록]", "McpPlugin", "[MCP", "ReflectorNet", "McpServer", "McpManager", "[AI]", "ConnectionManager", "EnsureConnection" };

        static void OnLogMessage(string condition, string stackTrace, LogType type)
        {
            if (!IsRecording || condition == null) return;
            foreach (var ig in IgnoreLogs) if (condition.Contains(ig)) return;
            bool isError = type == LogType.Error || type == LogType.Exception || type == LogType.Assert;
            if (!isError && type != LogType.Warning && !playing) return;   // 편집 중의 Debug.Log 는 도구 소음

            var msg = condition.Trim();
            if (msg.Length > 400) msg = msg.Substring(0, 400) + "…";
            var key = type + "|" + msg;
            lock (logLock)
            {
                if (logCounts.TryGetValue(key, out var n)) { logCounts[key] = n + 1; return; }
                logCounts[key] = 1;
            }
            string where = "";
            if (!string.IsNullOrEmpty(stackTrace))
            {
                foreach (var line in stackTrace.Split('\n'))
                {
                    int at = line.IndexOf("(at Assets/", StringComparison.Ordinal);
                    if (at >= 0) { where = line.Substring(at + 4).TrimEnd(')', '\r', ' '); break; }
                }
            }
            if (where != "") Log("log", "type", type.ToString(), "msg", msg, "where", where);
            else Log("log", "type", type.ToString(), "msg", msg);
        }

        static void FlushLogSummary()
        {
            List<string> items = new List<string>();
            lock (logLock)
            {
                foreach (var kv in logCounts)
                    if (kv.Value > 1)
                    {
                        int bar = kv.Key.IndexOf('|');
                        var m = kv.Key.Substring(bar + 1);
                        if (m.Length > 80) m = m.Substring(0, 80) + "…";
                        items.Add(kv.Key.Substring(0, bar) + " \"" + m + "\" ×" + kv.Value);
                    }
                logCounts.Clear();
            }
            if (items.Count > 0) Log("log_summary", "items", items);
        }

        // ───────────────────────── 파일 감시 + 사본 ─────────────────────────
        static readonly string[] SnapExt =
        {
            ".cs", ".unity", ".prefab", ".mat", ".asset", ".asmdef", ".shader", ".json", ".inputactions",
            ".controller", ".anim", ".physicmaterial", ".physicsmaterial", ".uxml", ".uss", ".txt", ".md",
        };
        const long MaxSnapBytes = 2 * 1024 * 1024;

        static readonly List<FileSystemWatcher> watchers = new List<FileSystemWatcher>();
        static readonly ConcurrentDictionary<string, DateTime> dirtyFiles = new ConcurrentDictionary<string, DateTime>();
        static readonly Dictionary<string, string> lastHash = new Dictionary<string, string>();
        static int snapSeq;

        static bool Wanted(string full)
        {
            var p = full.Replace('\\', '/');
            var ext = Path.GetExtension(p).ToLowerInvariant();
            if (Array.IndexOf(SnapExt, ext) < 0) return false;
            if (p.EndsWith("~")) return false;
            if (p.Contains("/Library/") || p.Contains("/Temp/") || p.Contains("/obj/") || p.Contains("/.git/") || p.Contains("/recordings/")) return false;
            return true;
        }

        static void StartWatcher()
        {
            StopWatcher();
            foreach (var sub in new[] { "Assets", "ProjectSettings" })
            {
                var dir = ProjectRoot + "/" + sub;
                if (!Directory.Exists(dir)) continue;
                try
                {
                    var w = new FileSystemWatcher(dir)
                    {
                        IncludeSubdirectories = true,
                        NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.FileName | NotifyFilters.Size,
                        InternalBufferSize = 64 * 1024,
                    };
                    w.Changed += (s, e) => MarkDirty(e.FullPath);
                    w.Created += (s, e) => MarkDirty(e.FullPath);
                    w.Renamed += (s, e) => MarkDirty(e.FullPath);
                    w.EnableRaisingEvents = true;
                    watchers.Add(w);
                }
                catch (Exception e) { Log("error", "where", "watcher", "msg", e.Message); }
            }
        }

        static void StopWatcher()
        {
            foreach (var w in watchers) { try { w.EnableRaisingEvents = false; w.Dispose(); } catch { } }
            watchers.Clear();
        }

        static void MarkDirty(string full)
        {
            if (!Wanted(full)) return;
            dirtyFiles[full.Replace('\\', '/')] = DateTime.Now;
        }

        static void FlushDirtyFiles(DateTime now, bool force)
        {
            if (dirtyFiles.Count == 0) return;
            foreach (var kv in dirtyFiles.ToArray())
            {
                if (!force && (now - kv.Value).TotalSeconds < 0.4) continue;   // 편집기가 여러 번에 나눠 쓰는 동안 기다린다
                DateTime dummy;
                dirtyFiles.TryRemove(kv.Key, out dummy);
                SnapshotFile(kv.Key, kv.Value, false);
            }
        }

        static void SnapshotFile(string full, DateTime when, bool baseline)
        {
            if (!File.Exists(full)) return;
            var rel = Rel(full);
            byte[] bytes;
            try
            {
                var fi = new FileInfo(full);
                if (fi.Length > MaxSnapBytes) return;
                bytes = File.ReadAllBytes(full);
            }
            catch (IOException) { dirtyFiles[full] = DateTime.Now; return; }   // 아직 쓰는 중 → 다음 틱에 다시
            catch (Exception) { return; }

            string sha;
            using (var h = SHA1.Create()) sha = BitConverter.ToString(h.ComputeHash(bytes)).Replace("-", "").Substring(0, 12).ToLowerInvariant();
            string prev;
            bool hadPrev = lastHash.TryGetValue(rel, out prev);
            if (hadPrev && prev == sha) return;

            int seq = baseline ? 0 : ++snapSeq;
            if (!baseline) EditorPrefs.SetInt(K + "snap", snapSeq);
            var name = seq.ToString("D4") + "__" + rel.Replace('/', '_').Replace("\\", "_");
            var snapRel = "snapshots/" + name;
            try
            {
                File.WriteAllBytes(SessionDir + "/" + snapRel, bytes);
                File.AppendAllText(SessionDir + "/snapshots/index.tsv",
                    seq + "\t" + rel + "\t" + sha + "\t" + name + "\t" + when.ToString("yyyy-MM-dd'T'HH:mm:ss.fff") + "\n", Utf8);
            }
            catch (Exception e) { Log("error", "where", "snapshot", "msg", e.Message); return; }
            lastHash[rel] = sha;

            if (baseline) return;
            int lines = 0; foreach (var b in bytes) if (b == (byte)'\n') lines++;
            LogAt(when, "file", "path", rel, "snap", snapRel, "bytes", bytes.Length, "lines", lines + 1, "created", !hadPrev);
        }

        static void Baseline()
        {
            int count = 0;
            foreach (var sub in new[] { "Assets", "ProjectSettings" })
            {
                var dir = ProjectRoot + "/" + sub;
                if (!Directory.Exists(dir)) continue;
                foreach (var f in Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories))
                {
                    if (!Wanted(f)) continue;
                    if (++count > 3000) { Log("error", "where", "baseline", "msg", "파일이 3000개를 넘어 기준 사본을 일부만 떴다"); return; }
                    SnapshotFile(f.Replace('\\', '/'), DateTime.Now, true);
                }
            }
        }

        static void LoadSnapshotIndex()
        {
            lastHash.Clear();
            var idx = SessionDir + "/snapshots/index.tsv";
            if (!File.Exists(idx)) return;
            foreach (var line in File.ReadAllLines(idx))
            {
                var c = line.Split('\t');
                if (c.Length >= 3) lastHash[c[1]] = c[2];
            }
        }

        // ───────────────────────── 에셋 생성·삭제·이동 ─────────────────────────
        static readonly HashSet<string> knownAssets = new HashSet<string>();
        static string KnownPath => SessionDir + "/known_assets.txt";

        static void InitKnownAssets()
        {
            knownAssets.Clear();
            foreach (var p in AssetDatabase.GetAllAssetPaths())
                if (p.StartsWith("Assets/", StringComparison.Ordinal)) knownAssets.Add(p);
            File.WriteAllLines(KnownPath, knownAssets, Utf8);
        }

        static void LoadKnownAssets()
        {
            knownAssets.Clear();
            if (File.Exists(KnownPath)) foreach (var l in File.ReadAllLines(KnownPath)) if (l.Length > 0) knownAssets.Add(l);
        }

        internal static void OnAssetsChanged(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            if (!IsRecording) return;
            bool dirty = false;
            for (int i = 0; i < moved.Length; i++)
            {
                if (!moved[i].StartsWith("Assets/", StringComparison.Ordinal)) continue;
                Log("asset_move", "from", movedFrom[i], "asset", moved[i]);
                knownAssets.Remove(movedFrom[i]); knownAssets.Add(moved[i]); dirty = true;
            }
            foreach (var p in deleted)
            {
                if (!p.StartsWith("Assets/", StringComparison.Ordinal)) continue;
                Log("asset_delete", "asset", p);
                knownAssets.Remove(p); dirty = true;
            }
            foreach (var p in imported)
            {
                if (!p.StartsWith("Assets/", StringComparison.Ordinal)) continue;
                if (knownAssets.Add(p))
                {
                    var t = AssetDatabase.GetMainAssetTypeAtPath(p);
                    Log("asset_create", "asset", p, "type", t != null ? t.Name : (AssetDatabase.IsValidFolder(p) ? "Folder" : "?"));
                    dirty = true;
                }
                else if (!Wanted(p) && !AssetDatabase.IsValidFolder(p))
                {
                    Log("asset_import", "asset", p);   // 사본을 안 뜨는 종류(그림 등)의 변경
                }
            }
            if (dirty) { try { File.WriteAllLines(KnownPath, knownAssets, Utf8); } catch { } }
            Drain();
        }

        // ───────────────────────── 유틸 ─────────────────────────
        static DateTime ParseIso(string s, DateTime fallback)
        {
            DateTime t;
            return DateTime.TryParse(s, Inv, DateTimeStyles.RoundtripKind, out t) ? t : fallback;
        }

        static string StableHash(string s)
        {
            unchecked
            {
                uint h = 2166136261;
                foreach (var c in s) { h ^= c; h *= 16777619; }
                return h.ToString("x8");
            }
        }
    }

    /// <summary>에셋 생성·삭제·이동은 임포트 파이프라인에서만 알 수 있다.</summary>
    class ChangeRecorderAssetHook : AssetPostprocessor
    {
        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            if (!ChangeRecorder.IsRecording) return;
            ChangeRecorder.OnAssetsChanged(imported, deleted, moved, movedFrom);
        }
    }
}
