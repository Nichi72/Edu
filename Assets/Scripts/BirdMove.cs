using UnityEngine;
using UnityEngine.InputSystem;
/// <summary>
/// # 플레이어 무브
// 지속적으로 중력을 받는다.
// 플레이어의 의지에 상관없이 앞으로 계속 나아간다.
// 플레이어의 스페이스나 왼쪽 클릭을 입력 받으면 점프를 한다.
/// </summary>
public class BirdMove : MonoBehaviour
{
    public float gravity = 5f; // 중력 가속도
    float speed = 5f; // 이동 속도
    float jumpPower = 5f; // 점프 힘


    void Update()
    {
        Debug.Log(Keyboard.current.spaceKey.wasPressedThisFrame);
        // ~ 하면 if문
        if(Keyboard.current.spaceKey.wasPressedThisFrame) // 스페이스 키를 눌렀을 때 True가 반환되는 변수를 가져옴.
        {
            transform.Translate(Vector3.up * jumpPower * Time.deltaTime); // 점프
        }
        transform.Translate(speed * Vector3.right * Time.deltaTime); // 앞으로 나아가는 속도
        transform.Translate(gravity * Vector3.down *Time.deltaTime); //

        
    }
}
