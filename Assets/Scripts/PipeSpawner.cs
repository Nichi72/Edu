using UnityEngine;

public class PipeSpawner : MonoBehaviour
{
    public GameObject pipePrefab;

    void Start()
    {
        Instantiate(pipePrefab, new Vector3(11f, 0f, 0f), Quaternion.identity);
    }
}
