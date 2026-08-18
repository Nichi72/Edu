using UnityEngine;

public class BirdMove : MonoBehaviour
{
    void Update()
    {
        float fallSpeed = 0.05f;

        transform.position += new Vector3(0f, -fallSpeed, 0f);
    }
}
