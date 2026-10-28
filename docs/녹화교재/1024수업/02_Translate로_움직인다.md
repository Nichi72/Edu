# 02. 플레이어 — 기본적인 이동 로직

<!--
상태:     4차 (강조 · 문장 줄임, 견본)
번호:     임시. 세 챕터 중 둘째
파일:     Assets/Script/BirdMove.cs
재료:     재료/타임라인_A.md  (영상 A 22:41–62:10)
영상파일: D:/4_Record/1024수업/2026-10-22 15-06-45.mp4
분량:     수업에서 강의 약 20분 + 실습 약 30분
시작상태: 01 끝. BirdMove.cs 맨 위에 플레이어 기획 주석, float speed; , 빈 Update
끝상태:   기록기 최종본에서 시연용 isBool 을 뺀 것
-->

> **이번 시간에 만드는 것** — Play 를 누르면 이렇게 된다.
> 1. 새가 오른쪽으로 계속 날아간다
> 2. 날아가면서 천천히 떨어진다
> 3. 날아가는 속도와 떨어지는 속도를 코드를 열지 않고 Unity 에서 바꿀 수 있다
> 4. 스페이스를 누르면 새가 반응한다. 다만 점프는 아직 어색하다

**이번에 배우는 말** — [단위 벡터](#s2) · [하드코딩](#s2) · [가독성](#s2) · [public](#s3) · [Keyboard](#s4) · [if](#s4)

이번에 정해지는 이름이다. ==철자와 대소문자까지 이대로 쓴다.==

| 이름 | 무엇 | 값 |
|---|---|---|
| `speed` | 오른쪽으로 가는 속도 | 5 |
| `gravitySpeed` | 아래로 떨어지는 속도 | 코드 5, Inspector 1.5 |
| `jumpPower` | 점프할 때 올라가는 양 | 5 |

---

## 시작하기 전에

- [ ] 01 을 끝냈다. `BirdMove.cs` 맨 위에 플레이어 기획이 주석으로 있다
- [ ] `transform.Translate` 로 물체를 움직여 본 적이 있다
- [ ] `Time.deltaTime` 을 곱하면 컴퓨터마다 프레임이 달라도 같은 속도가 된다는 것을 들었다

---

## 오른쪽으로 계속 나아감

```기획서
플레이어 — 기본적인 이동 로직
▶ 1. 오른쪽으로 계속 나아감
· 2. 중력으로 인해서 계속 아래로 떨어짐
· 3. 스페이스를 통해 점프
    위 방향으로 스페이스를 눌렀을때 점프를 한다.
```

==Play 하면 새가 오른쪽으로 계속 날아가게 만든다.== 지금은 가만히 있다.

이걸 하려면 세 가지가 필요하다. 모두 지난 시간에 본 것이다.

- **계속** 일어나는 일이다 → 매 프레임 도는 `Update` 에 쓴다
- 물체를 조금씩 옮긴다 → `transform.Translate`
- 방향은 **오른쪽** → `Vector3.right`

```csharp
    void Update()
    {
        transform.Translate(Vector3.right * 5 * Time.deltaTime);
    }
```

**Play.** 새가 오른쪽으로 간다.

> **단위 벡터** — `Vector3.right` 는 길이가 1 인 오른쪽, (1, 0, 0) 이다. ==방향만 알려 준다. 얼마나 갈지는 곱해서 정한다.== `* 5` 면 1초에 5칸.

이 `5` 는 무슨 숫자일까? 방금 쳤으니 지금은 안다. **석 달 뒤의 나는 모른다.**

> **하드코딩** — ==숫자를 코드에 그대로 박아 넣는 것.== 코드가 읽히는 정도를 **가독성** 이라고 한다. 하드코딩을 하면 가독성이 떨어진다.

그래서 숫자에 이름을 붙인다. ==`speed` 에 5 를 넣고, `5` 자리에 `speed` 를 쓴다.==

```csharp 전
    float speed;

    void Update()
    {
        transform.Translate(Vector3.right * 5 * Time.deltaTime);
    }
```
```csharp 후
    float speed = 5;

    void Update()
    {
        transform.Translate(Vector3.right * speed * Time.deltaTime);
    }
```

**Play.** 아까와 똑같이 간다. 움직임은 그대로, 코드만 「오른쪽 × 속도 × 시간」 으로 읽힌다.

마지막으로 기획 첫 줄에 `1.` 을 붙이고, 그 줄을 복사해 코드 바로 위에 붙인다. ==기획 한 줄 아래에 그 코드.== 앞으로 계속 이렇게 짝을 맞춘다.

```csharp 전
        transform.Translate(Vector3.right * speed * Time.deltaTime);
```
```csharp 후
        // 1. 오른쪽으로 계속 나아감.
        transform.Translate(Vector3.right * speed * Time.deltaTime);
```

---

## 중력으로 인해서 계속 아래로 떨어짐

```기획서
플레이어 — 기본적인 이동 로직
✓ 1. 오른쪽으로 계속 나아감
▶ 2. 중력으로 인해서 계속 아래로 떨어짐
· 3. 스페이스를 통해 점프
    위 방향으로 스페이스를 눌렀을때 점프를 한다.
```

==Play 하면 새가 오른쪽으로 날아가면서 아래로도 떨어지게 만든다.==

> 멈춤 — 오른쪽으로 가는 줄은 이미 있다. 떨어지는 줄은 그 줄과 무엇만 다르면 될까?

두 가지가 다르다.

- 방향이 **아래** → `Vector3.down`
- 빠르기가 다르다 → 변수를 하나 더, `gravitySpeed`

```csharp 전
    float speed = 5;

    void Update()
    {
        // 1. 오른쪽으로 계속 나아감.
        transform.Translate(Vector3.right * speed * Time.deltaTime);
    }
```
```csharp 후
    float speed = 5;
    float gravitySpeed = 5;

    void Update()
    {
        // 1. 오른쪽으로 계속 나아감.
        transform.Translate(Vector3.right * speed * Time.deltaTime);

        // 2. 중력으로 인해서 계속 아래로 떨어짐
        transform.Translate(Vector3.down * gravitySpeed * Time.deltaTime);
    }
```

`gravitySpeed` — 소문자로 시작, 둘째 단어부터 대문자. 01 의 이름 규칙이다.

**Play.** 오른쪽으로 가면서 떨어진다. 그런데 ==너무 빨리 떨어진다.==

알맞은 빠르기를 찾으려면 숫자를 여러 번 바꿔 봐야 한다. 그때마다 코드를 열고, 고치고, 저장하고, Play. 귀찮다. ==코드를 열지 않고 숫자를 바꾸는 방법이 필요하다.==

```csharp 전
    float speed = 5;
    float gravitySpeed = 5;
```
```csharp 후
    public float speed = 5;
    public float gravitySpeed = 5;
```

`Bird` 를 클릭한다. Inspector 의 Bird Move 칸에 **Speed** 와 **Gravity Speed** 가 생겼다. Play 중에 Gravity Speed 를 바꿔 보자. 바로 바뀐다.

> **public** — ==변수 앞에 붙이면 Inspector 에 칸이 생긴다.== 코드를 안 열고, Play 중에도 값을 바꿀 수 있다. 안 붙인 변수는 그 스크립트 안에서만 쓴다.

==Play 중에 바꾼 값은 Stop 하면 돌아간다.== 알맞은 값을 찾았으면 **Stop 한 뒤에** Gravity Speed 를 **1.5** 로 넣고 씬을 저장한다 (Ctrl + S).

> 멈춤 — 코드에는 5, Inspector 에는 1.5 다. 지금 새는 어느 값으로 떨어지나?

==Inspector 의 값이다.== Inspector 에 들어간 값이 코드의 숫자보다 앞선다.

---

## 스페이스를 통해 점프

```기획서
플레이어 — 기본적인 이동 로직
✓ 1. 오른쪽으로 계속 나아감
✓ 2. 중력으로 인해서 계속 아래로 떨어짐
▶ 3. 스페이스를 통해 점프
    위 방향으로 스페이스를 눌렀을때 점프를 한다.
```

==스페이스를 누르면 새가 위로 점프하게 만든다.== 이걸 하려면 두 가지가 필요하다.

1. **스페이스를 눌렀는지** 알아내기
2. **눌렀을 때만** 점프하기

### 필요한 것 1 — 스페이스를 눌렀는지 알아내기

Unity 에는 키보드 상태를 알려 주는 `Keyboard` 가 있다. 이렇게 쓴다.

```csharp
Keyboard.current.spaceKey.wasPressedThisFrame
```

==이번 프레임에 스페이스를 눌렀으면 `true`, 아니면 `false`.== 지금은 이런 게 있다는 것만 알면 된다.

> **Keyboard** — 키보드 입력을 알려 주는 것. 맨 위 `using UnityEngine.InputSystem;` 상자에 들어 있다 (01 에서 적어 둔 줄). **이 줄이 없으면 `Keyboard` 에 빨간 줄이 생긴다.**

### 필요한 것 2 — 눌렀을 때만 하기

> 멈춤 — 앞으로 가기와 떨어지기는 매 프레임 한다. 점프도 매 프레임 하나?

점프는 눌렀을 때만 한다. **「~ 할 때만」 을 코드로 쓰는 것이 `if` 다.**

> **if** — ==괄호 안이 `true` 면 중괄호 안을 하고, `false` 면 건너뛴다.== 괄호 안에는 참/거짓 값(bool)이 들어간다. 더 깊게 보려면 [if 정리](concept-if.html).

### 둘을 합친다

점프부터 넣지 않는다. ==누른 순간을 잘 잡는지 Console 로 먼저 확인한다.==

```csharp
        // 3. 스페이스를 통해 점프
        // 위 방향으로 스페이스를 눌렀을때 점프를 한다.

        if(Keyboard.current.spaceKey.wasPressedThisFrame) // 스페이스를 눌렀을 때 
        {
            Debug.Log("스페이스를 눌렀습니다");
        }
```

**Play** 하고 스페이스를 몇 번 눌러 보자. ==누를 때마다 Console 에 한 줄씩 찍힌다.== Update 가 매 프레임 「눌렀니?」 하고 묻고, 누른 그 프레임에만 들어간 것이다.

조건이 잘 들어오니 점프를 넣는다. 떨어지는 줄을 복사해 방향을 위로, 숫자는 변수로.

```csharp 전
    public float gravitySpeed = 5;

    void Update()
    {
        // … 1 · 2 는 그대로 …

        if(Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            Debug.Log("스페이스를 눌렀습니다");
        }
    }
```
```csharp 후
    public float gravitySpeed = 5;
    public float jumpPower = 5;

    void Update()
    {
        // … 1 · 2 는 그대로 …

        if(Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            Debug.Log("스페이스를 눌렀습니다");
            // 점프를 한다.
            transform.Translate(Vector3.up * jumpPower * Time.deltaTime);
        }
    }
```

**Play.** 로그는 찍힌다. 그런데 ==새가 점프하는 것 같지가 않다.==

> **다음 시간 질문** — 조건은 분명히 들어온다. 그런데 왜 점프처럼 안 보일까?

---

## 확인하기

- [ ] Play 하면 새가 오른쪽으로 날아가면서 천천히 떨어진다
- [ ] Inspector 에 Speed · Gravity Speed · Jump Power 세 칸이 있고, 바꾸면 움직임이 바뀐다
- [ ] 스페이스를 누를 때마다 Console 에 「스페이스를 눌렀습니다」 가 한 줄씩 찍힌다
- [ ] 점프가 점프 같지 않다. **이게 맞다.** 다음 시간에 고친다

---

## 안 되면

- **`Debug.Log("...")` 줄에 빨간 줄** → ==뒤에 `;` 를 빼먹었다.==
- **변수 줄을 복사했더니 빨간 줄** → ==이름을 안 바꿔서 같은 이름이 둘이다.==
- **코드의 숫자를 바꿨는데 그대로다** → ==Inspector 의 값이 앞선다.== Inspector 에서 바꾼다.

---

## 답 — 이 시간이 끝났을 때의 코드

여기까지 스스로 해봤다면 봐도 된다.

```csharp
using UnityEngine;
using UnityEngine.InputSystem;
// 일괄 주석 컨트롤 + K , 컨트롤 + C
// 일괄 주석 컨트롤 + K , 컨트롤 + U

// 플레이어
// 기본적인 이동 로직
// 1. 오른쪽으로 계속 나아감.
// 2. 중력으로 인해서 계속 아래로 떨어짐
// 3. 스페이스를 통해 점프
// 위 방향으로 스페이스를 눌렀을때 점프를 한다.

public class BirdMove : MonoBehaviour
{
    public float speed = 5;
    public float gravitySpeed = 5;
    public float jumpPower = 5;

    void Update()
    {
        // 1. 오른쪽으로 계속 나아감.
        transform.Translate(Vector3.right * speed * Time.deltaTime);

        // 2. 중력으로 인해서 계속 아래로 떨어짐
        transform.Translate(Vector3.down * gravitySpeed * Time.deltaTime);

        // 3. 스페이스를 통해 점프
        // 위 방향으로 스페이스를 눌렀을때 점프를 한다.

        if(Keyboard.current.spaceKey.wasPressedThisFrame) // 스페이스를 눌렀을 때 
        {
            Debug.Log("스페이스를 눌렀습니다");
            // 점프를 한다.
            transform.Translate(Vector3.up * jumpPower * Time.deltaTime);
        }
    }

}
```

Inspector 의 Gravity Speed 는 1.5 로 저장돼 있다.

---

<!--
═══════════ 교수용 ═══════════

4차에서 바꾼 것 (10-28 「글을 잘 안 읽는다」)
  - 꼭 읽어야 하는 한 문장에 ==형광펜== (절마다 「만들 것」, 개념 상자의 핵심, 주의, 멈춤의 답)
  - **Play.** 를 ▶ Play 표시로. 긴 문장을 줄였다

3차에서 바꾼 것 (10-28 2차 피드백 · 「필요에 의해서 배운다」)
  - 챕터 제목을 기획서 덩어리 「플레이어 — 기본적인 이동 로직」 으로
  - 절 제목을 기획서 문장 그대로. 절마다 맨 앞에 기획서 카드 (끝낸 줄 ✓, 지금 줄 강조)
  - 「Unity 에서 값을 바꾼다」 절을 없애고 중력 절 안으로. 떨어지는 속도를 맞추려니 public 이 필요해진다
  - 절마다 「이걸 하려면 필요한 것」 → 배운다 → 만든다 → Play
  - 코드 변경은 전·후를 나란히. 새 줄 초록, 바뀐 칸 강조
  - 점프 절: 필요한 것 1 Keyboard (「이런 게 있다」 수준) / 필요한 것 2 if. bool · using 은 상자를 없애고 if · Keyboard 설명 안의 한 줄로
  - wasPressed / wasReleased 표를 뺐다
  - if 는 개념 정리 페이지(concept-if.html)로 링크. else · else if · 비교 연산자는 거기에

2차에서 바꾼 것 (10-28 1차 피드백)
  - 「이번 시간에 만드는 것」 을 결과물로, 용어 표 없앰, 학생 본문에서 영상 시각 뺌

수업과 순서가 다른 곳
  - public: 수업에서는 speed 를 만들자마자 public 으로 뺐다 (A 25:54). 교재는 중력까지 만든 뒤 필요해서 간다
  - isBool 시연 (A 51:46–55:05): 교재 본문에서 뺐다. if 정리 페이지의 else 예제로 옮겼다
  - else if / else (A 54:16): if 정리 페이지로
  - VS Code 테마 Dark Modern (A 61:01): 교재에서 뺐다. 수업 진행용

시연 순서와 영상 시각 (영상 A. 괄호는 기록기 경과)
  22:41 「우리 이거 배웠죠? transform.Translate」     23:16 (01:06) right * 5 * deltaTime 저장
  23:03 단위 벡터 × 5 · deltaTime 복습               23:56 하드코딩 · 가독성
  24:28 (02:18) speed = 5 → 24:31 speed 로 바꿈       25:44 (03:34) Play
  25:54 「밸런스 요소, 귀찮다」 → 26:04 (03:54) public  26:17 Play 중 Speed 5 → −3.43 → −1.37
  26:43 (04:33) 기획 주석을 코드 위에 복사
  27:55 2번 중력 — 복붙 → down → gravitySpeed         29:10 Inspector 5 → 1 → 1.5, 씬 저장
  29:16 Play → 29:36 「여기까지 해 보세요」 → 실습 20분
  49:39 3번 점프 · 조건문                             50:39 「조건문이 프로그래밍의 절반」
  51:46 기본형 네 개 복습 → isBool 시연               54:16 else if / else 쳐 보이고 지움
  55:40 using = 도구 상자                             56:49 wasPressed / wasReleased
  57:53 (35:43) Debug.Log 로 확인                     58:47 (36:37) 점프 줄 · jumpPower
  59:36 (37:26) Play → 59:51 「의도된 버그」            61:01 VS Code 테마 → 62:10 실습 · 쉬는 시간

다음 시간에 짚을 것
  - 점프가 거의 안 보인 직접 원인: 한 번 일어나는 점프에 Time.deltaTime 을 곱했다. 60fps 에서 5 × 1/60 ≈ 0.08칸
-->
