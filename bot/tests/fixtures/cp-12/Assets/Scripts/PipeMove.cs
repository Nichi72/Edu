using UnityEngine;

public class PipeMove : MonoBehaviour
{
    public float speed = 3f;

    void Update()
    {
        transform.position += new Vector3(-speed * Time.deltaTime, 0f, 0f);
    }
}
