using UnityEngine;

public class BirdMove : MonoBehaviour
{
    public float fallSpeed = 3f;

    void Update()
    {
        transform.position += new Vector3(0f, -fallSpeed * Time.deltaTime, 0f);
    }
}
