using UnityEngine;

public class PipeSpawner : MonoBehaviour
{
    public GameObject pipePrefab;
    public float spawnInterval = 2f;

    float timer = 0f;

    void Update()
    {
        timer += Time.deltaTime;

        if (timer >= spawnInterval)
        {
            Instantiate(pipePrefab, new Vector3(11f, 0f, 0f), Quaternion.identity);
            timer = 0f;
        }
    }
}
