using UnityEngine;
using UnityEngine.InputSystem;

public class BirdMove : MonoBehaviour
{
    public float fallSpeed = 3f;
    public float jumpPower = 1.5f;

    bool isDead = false;

    void Update()
    {
        if (!isDead)
        {
            transform.position += new Vector3(0f, -fallSpeed * Time.deltaTime, 0f);

            if (Keyboard.current.spaceKey.wasPressedThisFrame)
            {
                transform.position += new Vector3(0f, jumpPower, 0f);
            }

            if (transform.position.y > 4.5f)
            {
                transform.position = new Vector3(-3f, 4.5f, 0f);
            }

            if (transform.position.y >= 4.5f || transform.position.y <= -3.5f)
            {
                isDead = true;
                Debug.Log("Dead");
            }
        }
    }
}
