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
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "python",
                    Arguments = "\"" + script + "\" \"" + dir + "\"",
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
                    string err = p.StandardError.ReadToEnd();
                    string outp = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(60000);
                    if (p.ExitCode == 0 && File.Exists(dir + "/report.md"))
                        EditorUtility.OpenWithDefaultApp(dir + "/report.md");
                    else
                        EditorUtility.DisplayDialog("수업 기록", "보고서 생성 실패\n\n" + outp + "\n" + err, "확인");
                }
            }
            catch (Exception e)
            {
                EditorUtility.DisplayDialog("수업 기록", "python 을 실행하지 못했습니다: " + e.Message + "\n\n기록 폴더를 교재 프로젝트로 가져가서\npython tools/record-report.py 를 실행하세요.", "확인");
            }
        }
    }
}
