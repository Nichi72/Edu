using UnityEngine;
using UnityEngine.InputSystem;

public class BirdMove : MonoBehaviour
{
    public float jumpPower = 5f;

    Rigidbody rb;
    bool isDead = false;

    void Start()
    {
        rb = GetComponent<Rigidbody>();
    }

    void Update()
    {
        if (!isDead)
        {
            if (Keyboard.current.spaceKey.wasPressedThisFrame)
            {
                rb.linearVelocity = new Vector3(0f, jumpPower, 0f);
            }

            if (transform.position.y >= 4.5f || transform.position.y <= -3.5f)
            {
                isDead = true;
                Debug.Log("Dead");
            }
        }
    }
}
