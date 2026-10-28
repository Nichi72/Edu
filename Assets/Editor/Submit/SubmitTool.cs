using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace ClassSubmit
{
    /// <summary>
    /// 메뉴 「제출」. 학생이 손댄 것(스크립트·씬·프리팹·머티리얼·설정 일부)만 zip 으로 묶는다.
    /// 만든 zip 을 디스코드 채점 봇 DM 에 올리면 된다. 선생님도 같은 버튼으로 기준(정답지)을 만든다.
    /// 이 폴더(Assets/Editor/Submit)만 복사하면 다른 프로젝트에서도 돈다. 빌드에는 안 들어간다.
    /// </summary>
    public static class SubmitTool
    {
        const string OutFolder = "제출";
        const int FormatVersion = 1;
        const long MaxFileBytes = 2L * 1024 * 1024;   // 이보다 큰 파일은 뺀다. 모델·텍스처는 채점에 안 쓴다
        const long WarnZipBytes = 8L * 1024 * 1024;   // 디스코드 첨부 한도(10 MB) 근처면 경고

        static readonly HashSet<string> AssetExts = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            ".cs", ".unity", ".prefab", ".mat", ".asmdef", ".physicmaterial", ".physicsmaterial",
            ".anim", ".controller", ".inputactions"
        };
        // 이 이름의 폴더는 통째로 뺀다. 에디터 도구(튜터·기록기·이 스크립트)와 플러그인은 학생 작업이 아니다
        static readonly HashSet<string> SkipDirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            { "Editor", "Plugins", "StreamingAssets", "Gizmos" };
        static readonly string[] SettingsFiles =
        {
            "ProjectVersion.txt", "ProjectSettings.asset", "TagManager.asset", "EditorBuildSettings.asset",
            "InputManager.asset", "DynamicsManager.asset", "Physics2DSettings.asset", "TimeManager.asset", "QualitySettings.asset"
        };

        [MenuItem("제출/과제 zip 만들기", false, 1)]
        public static void MakeZip()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            { EditorUtility.DisplayDialog("제출", "Play 를 멈춘 뒤에 만든다.", "확인"); return; }
            if (EditorApplication.isCompiling)
            { EditorUtility.DisplayDialog("제출", "컴파일이 끝난 뒤에 다시 누른다.", "확인"); return; }

            // 저장 안 한 것이 있으면 저장한다. 안 하면 지난번 상태가 제출된다
            if (!EditorSceneManager.SaveOpenScenes())
            {
                if (!EditorUtility.DisplayDialog("제출", "씬을 저장하지 않았다.\n저장 안 된 상태로 묶을까?", "그래도 묶기", "취소"))
                    return;
            }
            AssetDatabase.SaveAssets();

            string root = Directory.GetParent(Application.dataPath).FullName;
            var files = new List<string>();
            var skipped = new List<string>();
            CollectAssets(root, Path.Combine(root, "Assets"), files, skipped);
            foreach (var s in SettingsFiles)
            {
                var p = Path.Combine(root, "ProjectSettings", s);
                if (File.Exists(p)) files.Add(p);
            }
            var manifest = Path.Combine(root, "Packages", "manifest.json");
            if (File.Exists(manifest)) files.Add(manifest);

            string outDir = Path.Combine(root, OutFolder);
            Directory.CreateDirectory(outDir);
            string zipPath = Path.Combine(outDir, Safe(new DirectoryInfo(root).Name) + "_" + DateTime.Now.ToString("yyyyMMdd_HHmm") + ".zip");
            try { WriteZip(zipPath, root, files, skipped); }
            catch (Exception e)
            {
                EditorUtility.DisplayDialog("제출", "zip 을 못 만들었다.\n" + e.Message, "확인");
                return;
            }

            long size = new FileInfo(zipPath).Length;
            var msg = new StringBuilder();
            msg.AppendLine("파일 " + files.Count + "개, " + Math.Max(1, size / 1024) + " KB");
            msg.AppendLine(zipPath);
            msg.AppendLine();
            msg.AppendLine("이 zip 을 디스코드 채점 봇 DM 에 올리면 된다.");
            if (skipped.Count > 0) msg.AppendLine("\n큰 파일 " + skipped.Count + "개는 뺐다. 채점에는 필요 없다.");
            if (size > WarnZipBytes) msg.AppendLine("\n주의: 디스코드 첨부 한도에 가깝다. 큰 에셋이 섞였는지 본다.");
            Debug.Log("[제출] " + zipPath);
            if (EditorUtility.DisplayDialog("제출 zip 완성", msg.ToString(), "폴더 열기", "닫기"))
                EditorUtility.RevealInFinder(zipPath);
        }

        [MenuItem("제출/제출 폴더 열기", false, 20)]
        static void OpenFolder()
        {
            string dir = Path.Combine(Directory.GetParent(Application.dataPath).FullName, OutFolder);
            if (!Directory.Exists(dir)) { EditorUtility.DisplayDialog("제출", "아직 만든 zip 이 없다. 「과제 zip 만들기」 부터.", "확인"); return; }
            EditorUtility.RevealInFinder(dir);
        }

        [MenuItem("제출/안내", false, 40)]
        static void Help()
        {
            EditorUtility.DisplayDialog("제출 안내",
                "1. 제출 ▸ 과제 zip 만들기\n" +
                "2. 열린 폴더의 zip 을 디스코드 채점 봇 DM 에 드래그\n" +
                "3. 봇이 몇 초 뒤 결과를 답한다. 미통과면 고쳐서 다시 올린다\n\n" +
                "zip 에는 스크립트·씬·프리팹·머티리얼과 프로젝트 설정 일부만 들어간다.", "확인");
        }

        static void CollectAssets(string root, string dir, List<string> files, List<string> skipped)
        {
            foreach (var sub in Directory.GetDirectories(dir))
            {
                var name = Path.GetFileName(sub);
                if (name.StartsWith(".") || name.EndsWith("~") || SkipDirs.Contains(name)) continue;
                CollectAssets(root, sub, files, skipped);
            }
            foreach (var f in Directory.GetFiles(dir))
            {
                if (!AssetExts.Contains(Path.GetExtension(f))) continue;
                if (new FileInfo(f).Length > MaxFileBytes) { skipped.Add(Rel(root, f)); continue; }
                files.Add(f);
                // .meta 의 GUID 가 있어야 씬이 어느 스크립트를 가리키는지 풀 수 있다
                if (File.Exists(f + ".meta")) files.Add(f + ".meta");
            }
        }

        static void WriteZip(string zipPath, string root, List<string> files, List<string> skipped)
        {
            var entries = new StringBuilder();
            using (var fs = new FileStream(zipPath, FileMode.Create))
            using (var zip = new ZipArchive(fs, ZipArchiveMode.Create))
            {
                foreach (var f in files)
                {
                    string rel = Rel(root, f);
                    var e = zip.CreateEntry(rel, System.IO.Compression.CompressionLevel.Optimal);
                    using (var src = File.OpenRead(f))
                    using (var dst = e.Open()) src.CopyTo(dst);
                    if (entries.Length > 0) entries.Append(",");
                    entries.Append("{\"path\":" + J(rel) + ",\"bytes\":" + new FileInfo(f).Length + ",\"sha1\":\"" + Sha1(f) + "\"}");
                }

                var skippedJson = new StringBuilder();
                foreach (var s in skipped) { if (skippedJson.Length > 0) skippedJson.Append(","); skippedJson.Append(J(s)); }

                // 봇이 읽는 꼬리표. JsonUtility 는 리스트를 못 다루므로 손으로 쓴다
                string manifest =
                    "{\n" +
                    "  \"format\": " + FormatVersion + ",\n" +
                    "  \"unity\": " + J(Application.unityVersion) + ",\n" +
                    "  \"product\": " + J(PlayerSettings.productName) + ",\n" +
                    "  \"project\": " + J(new DirectoryInfo(root).Name) + ",\n" +
                    "  \"created\": " + J(DateTime.Now.ToString("yyyy-MM-ddTHH:mm:sszzz")) + ",\n" +
                    "  \"user\": " + J(Environment.UserName) + ",\n" +
                    "  \"device\": " + J(ShortHash(SystemInfo.deviceUniqueIdentifier)) + ",\n" +
                    "  \"files\": [" + entries + "],\n" +
                    "  \"skipped\": [" + skippedJson + "]\n" +
                    "}\n";
                var m = zip.CreateEntry("submit-manifest.json", System.IO.Compression.CompressionLevel.Optimal);
                using (var w = new StreamWriter(m.Open(), new UTF8Encoding(false))) w.Write(manifest);
            }
        }

        static string Rel(string root, string path) => path.Substring(root.Length + 1).Replace('\\', '/');

        static string Safe(string name)
        {
            foreach (var c in Path.GetInvalidFileNameChars()) name = name.Replace(c, '_');
            return name.Replace(' ', '_');
        }

        static string Sha1(string path)
        {
            using (var sha = SHA1.Create())
            using (var s = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(s)).Replace("-", "").ToLowerInvariant();
        }

        // 기기 식별자는 그대로 안 남긴다. 같은 PC 에서 나온 제출인지만 알면 된다
        static string ShortHash(string s)
        {
            using (var sha = SHA1.Create())
                return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(s ?? ""))).Replace("-", "").Substring(0, 12).ToLowerInvariant();
        }

        static string J(string s)
        {
            var sb = new StringBuilder("\"");
            foreach (var c in s ?? "")
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default: if (c < ' ') sb.Append("\\u" + ((int)c).ToString("x4")); else sb.Append(c); break;
                }
            }
            return sb.Append('"').ToString();
        }
    }
}
