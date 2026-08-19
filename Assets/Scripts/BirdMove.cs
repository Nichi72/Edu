using UnityEngine;
using UnityEngine.InputSystem;

public class BirdMove : MonoBehaviour
{
    public float fallSpeed = 3f;
    public float jumpPower = 1.5f;

    void Update()
    {
        transform.position += new Vector3(0f, -fallSpeed * Time.deltaTime, 0f);

        if (Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            transform.position += new Vector3(0f, jumpPower, 0f);
        }
    }
}
