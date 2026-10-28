# 03. 플레이어 — 기본적인 이동 로직, 물리로 다시

<!--
상태:     2차 (ch02 견본 방식 적용)
번호:     임시. 세 챕터 중 셋째
파일:     Assets/Script/BirdMoveByRid.cs
재료:     재료/타임라인_B.md  (영상 B 02:23–30:19)
영상파일: D:/4_Record/1024수업/2026-10-22 16-50-10.mp4
분량:     수업에서 강의 약 28분
          기록기가 꺼져 있었다 (화면의 기록기 창이 「기록 안 함」). 코드는 화면에서 읽었다
시작상태: 02 끝. BirdMove 의 점프가 점프 같지 않다
끝상태:   Bird 에 Rigidbody · BirdMove(꺼짐) · BirdMoveByRid. rb 는 Inspector 로 연결
-->

> **이번 시간에 만드는 것** — Play 를 누르면 이렇게 된다.
> 1. 스페이스를 누르면 새가 위로 튀어 올랐다가 곡선을 그리며 떨어진다 — 진짜 점프
> 2. 중력 코드를 한 줄도 안 써도 새가 떨어진다
> 3. 새가 오른쪽으로 계속 날아간다

**이번에 배우는 말** — [터널링](#s2) · [Rigidbody](#s3) · [GetComponent](#s4) · [null](#s4) · [linearVelocity](#s4)

이번에 정해지는 이름이다. ==철자와 대소문자까지 이대로 쓴다.==

| 이름 | 무엇 | 값 |
|---|---|---|
| `BirdMoveByRid` | Rigidbody 로 움직이는 새 스크립트. **R · I · D** | — |
| `rb` | Bird 의 Rigidbody 를 담는 변수 | Inspector 로 연결 |
| `forwardSpeed` | 오른쪽으로 가는 속도 | 5 |
| `jumpPower` | 점프할 때 위로 주는 속도 | 코드 10, Inspector 5 |

---

## 시작하기 전에

- [ ] 02 를 끝냈다. 스페이스를 누르면 Console 에 로그는 찍히는데 점프가 점프 같지 않다

---

## 왜 점프 같지 않을까

```기획서
플레이어 — 기본적인 이동 로직
✓ 1. 오른쪽으로 계속 나아감
✓ 2. 중력으로 인해서 계속 아래로 떨어짐
▶ 3. 스페이스를 통해 점프
    02 에서 만들었지만 점프 같지 않다
```

==점프가 왜 이상한지 원인을 찾는다.==

Scene 뷰를 보면서 Play 하고, Inspector 의 Jump Power 를 10, 100, 300 으로 올려 본다. 100 쯤에서 깔짝 움직이고, 300 이면 크게 튄다. **그래도 플래피 버드의 점프가 아니다.**

> 멈춤 — 이걸 AI 에게 어떻게 설명할까? 원인을 모르면 설명도 못 한다.

원인은 `transform.Translate` 에 있다. ==Translate 는 사실 순간이동이다.== 매 프레임 위치를 조금씩 바꿔 끼우는 것이다. 그게 쌓여서 움직이는 것처럼 보일 뿐이다. 물리 엔진은 그 사이를 모른다.

> **터널링** — 물체가 한 번에 크게 옮겨지면서 ==그 사이에 있던 벽을 뚫고 지나가는 현상.== 점프 한 번에 5칸을 순간이동하면, 그 사이에 파이프가 있어도 지나간다.

속도가 쌓이지도 않으니, 올라갔다 내려오는 **관성** 느낌도 없다. ==Translate 로는 진짜 점프를 만들기 어렵다. 물리가 필요하다.==

> **한 가지 더** — 10 으로는 거의 안 움직인 이유는 따로 있다. 02 에서 점프에도 `Time.deltaTime` 을 곱했다. 점프는 누른 **한 프레임에만** 일어난다. 60fps 면 5 × 1/60 ≈ 0.08칸만 올라간다. ==계속 일어나는 일에는 곱하고, 한 번 일어나는 일에는 곱하지 않는다.==

---

## 중력으로 인해서 계속 아래로 떨어짐

```기획서
플레이어 — 기본적인 이동 로직 (물리로 다시)
· 1. 오른쪽으로 계속 나아감
▶ 2. 중력으로 인해서 계속 아래로 떨어짐
· 3. 스페이스를 통해 점프
    위 방향으로 스페이스를 눌렀을때 점프를 한다.
```

==중력을 코드가 아니라 물리 엔진에게 맡긴다.== 물리로 다시 만들 때는 중력이 제일 쉬워서 먼저 한다.

1. Hierarchy 에서 `Bird` 클릭
2. Inspector 맨 아래 **Add Component** → `Rigidbody` 검색 → 추가
3. ==Inspector 의 **Bird Move (Script)** 이름 옆 체크를 끈다.== 지우지는 않는다. Translate 로 만든 기록으로 남긴다

**Play.** ==코드 한 줄 없이 새가 떨어진다.== 그것도 점점 빨라지면서.

> **Rigidbody** — ==물리 엔진이 이 물체를 움직이게 맡기는 컴포넌트.== 붙이는 순간 중력을 받는다. 충돌 처리를 직접 만들지 않아도 된다. 이게 Unity 의 가장 큰 강점이다.

Play 중에 Rigidbody 의 **Use Gravity** 를 꺼 본다. 더 빨라지지 않고 그 순간의 속도 그대로 간다. 관성이다. 다시 켜면 다시 빨라지며 떨어진다.

움직이는 방식을 정리하면 이렇다.

| 방식 | 좋은 점 | 아쉬운 점 |
|---|---|---|
| `transform.Translate` | 단순하다. 계산이 빠르다. 내 뜻대로 정확히 놓인다 | 순간이동이다. 물리가 아니다 |
| `Rigidbody` | 물리 엔진이 중력 · 속도 · 충돌을 계산한다 | 내 뜻대로만 움직이지는 않는다 |

세 번째 방식(CharacterController)도 있다. 이번에는 다루지 않는다.

---

## 오른쪽으로 계속 나아감

```기획서
플레이어 — 기본적인 이동 로직 (물리로 다시)
▶ 1. 오른쪽으로 계속 나아감
✓ 2. 중력으로 인해서 계속 아래로 떨어짐
· 3. 스페이스를 통해 점프
    위 방향으로 스페이스를 눌렀을때 점프를 한다.
```

==Rigidbody 에게 「오른쪽으로 가」 라고 시킨다.== 이걸 하려면 세 가지가 필요하다.

1. Rigidbody 로 움직이는 **새 스크립트**
2. 그 스크립트가 Bird 의 Rigidbody 를 **손에 쥐는 방법**
3. Rigidbody 에게 **속도를 주는 방법**

### 필요한 것 1 — 새 스크립트

`Assets/Script` → 오른쪽 클릭 → **Create > Scripting > MonoBehaviour Script** → 이름 `BirdMoveByRid` → `Bird` 에 붙인다. ==이름은 **R · I · D**, Rigidbody 의 앞 세 글자다.==

### 필요한 것 2 — Rigidbody 를 손에 쥐기

02 에서는 `transform.Translate` 라고 썼다. Transform 컴포넌트의 기능을 쓴 것이다. 이번에는 Rigidbody 의 기능을 쓴다.

> 멈춤 — `Rigidbody.` 라고 바로 쓰면 될까? `Rigidbody` 가 대문자로 시작한다. 01 의 이름 규칙으로 보면 이건 무엇인가?

==대문자로 시작하니 클래스다. 클래스로 바로 쓰지 않고, 담을 변수를 만든다.==

```csharp
public class BirdMoveByRid : MonoBehaviour
{
    public Rigidbody rb;
```

`float speed` 와 모양이 같다. 그릇의 타입만 `float` 대신 `Rigidbody` 다.

이 그릇에 Bird 의 Rigidbody 를 넣는 방법은 둘이다.

**코드로 넣기** — `Start` 에서 찾아서 넣는다.

```csharp
    void Start()
    {
        rb = GetComponent<Rigidbody>();
    }
```

> **GetComponent** — ==내 오브젝트에 붙어 있는 컴포넌트를 찾아오는 함수.== `GetComponent<Rigidbody>()` 는 「내게 붙은 Rigidbody 를 줘」. MeshRenderer, Transform, Collider 도 같은 방법으로 찾는다.

그런데 Bird 에 Rigidbody 가 **없으면?** 찾아도 없다.

> **null** — ==아무것도 없다는 뜻. 0 과 다르다.== 0 은 값이 있는데 그 값이 0 이고, null 은 값 자체가 없다. 없는 것에서 무언가를 꺼내려 하면 에러가 난다.

| 휴지걸이에 | 뜻 |
|---|---|
| 휴지가 걸려 있다 | 값이 있다 (1) |
| 휴지심만 걸려 있다 | 값이 0 이다. 그래도 **있다** |
| 휴지심조차 없다 | **null**. 아예 없다 |

**Inspector 로 넣기** — `Bird` 의 Inspector 에서 Bird Move By Rid 의 **Rb** 칸을 본다. `None (Rigidbody)` 다. Hierarchy 의 `Bird` 를 그 칸으로 끌어다 놓는다. ==칸이 `Bird (Rigidbody)` 가 되면 연결된 것이다.==

**우리는 Inspector 로 넣는다.** 칸에 들어간 것을 눈으로 확인할 수 있고, 실행해 보지 않아도 알 수 있다. 그래서 코드로 넣는 줄은 주석으로 막아 둔다.

```csharp 전
        rb = GetComponent<Rigidbody>();
```
```csharp 후
        // rb = GetComponent<Rigidbody>();
```

> 용어 주의 — 코드로 넣기를 **동적 할당**, Inspector 로 넣기를 **정적 할당** 이라고 부르기도 한다. C# 책에서 「동적 할당」 은 보통 다른 뜻(`new` 로 메모리를 잡는 일)이니, 여기서는 이 뜻으로만 기억한다.

### 필요한 것 3 — 속도를 주기

```csharp
    void Start()
    {
        // rb = GetComponent<Rigidbody>();

        // 오른쪽으로움직이는 코드
        rb.linearVelocity = new Vector3(1,0,0);
    }
```

**Play.** 앞으로 간다. 그런데 이상한 점이 있다.

> 멈춤 — 02 의 Translate 는 Update 에 있어야 계속 갔다. 이 줄은 **Start** 에 있다. 한 번만 실행되는데 왜 계속 갈까?

> **linearVelocity** — Rigidbody 의 속도. ==위치를 옮기는 게 아니라 속도를 준다.== 한 번 속도를 주면 물리 엔진이 그 속도로 계속 옮긴다. 그래서 Start 에 한 번이면 된다.

`1,0,0` 의 1 은 하드코딩이다. 변수로 뺀다.

```csharp 전
    public Rigidbody rb;

    void Start()
    {
        rb.linearVelocity = new Vector3(1,0,0);
    }
```
```csharp 후
    public Rigidbody rb;
    public float forwardSpeed = 5;

    void Start()
    {
        rb.linearVelocity = new Vector3(forwardSpeed,0,0);
    }
```

**중력 코드는 안 쓴다.** Rigidbody 의 Use Gravity 가 이미 하고 있다.

---

## 스페이스를 통해 점프

```기획서
플레이어 — 기본적인 이동 로직 (물리로 다시)
✓ 1. 오른쪽으로 계속 나아감
✓ 2. 중력으로 인해서 계속 아래로 떨어짐
▶ 3. 스페이스를 통해 점프
    위 방향으로 스페이스를 눌렀을때 점프를 한다.
```

==스페이스를 누르면 새가 위로 튀어 오르게 만든다.== 이번엔 진짜 점프다.

이걸 하려면 두 가지가 필요하다.

- 스페이스를 눌렀을 때만 → **02 와 똑같은 `if`**
- 위로 튀어 오르기 → 위치를 옮기지 말고 **위로 속도를 준다**

새 스크립트에는 `using UnityEngine.InputSystem;` 이 없다. ==`Keyboard` 에 빨간 줄이 생기면 맨 위에 그 줄을 넣는다.==

02 의 점프와 나란히 놓고 보자.

```csharp 전 BirdMove.cs
        if(Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            transform.Translate(Vector3.up * jumpPower * Time.deltaTime);
        }
```
```csharp 후 BirdMoveByRid.cs
        if(Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            rb.linearVelocity = new Vector3(forwardSpeed,jumpPower,0);
        }
```

`if` 는 그대로다. ==바뀐 건 중괄호 안 한 줄 — 위치를 옮기던 것이 속도를 주는 것으로.==

변수도 하나 더 만든다.

```csharp
    public float jumpPower = 10;
```

> 멈춤 — 점프인데 왜 x 칸에 `forwardSpeed` 를 넣었을까? 0 을 넣으면 어떻게 될까?

==속도를 통째로 새로 주기 때문이다.== x 에 0 을 넣으면 점프할 때마다 앞으로 가던 속도가 사라져 그 자리에서 뛴다.

**Play.** ==올라갔다가 곡선을 그리며 내려온다.== 진짜 점프다. 10 은 너무 세다. Inspector 에서 **Jump Power 를 5** 로. **값은 직접 플레이해 보면서 찾는 것이다.**

---

## 확인하기

- [ ] Bird 에 Rigidbody 가 있고, Bird Move (Script) 는 꺼져 있다
- [ ] Bird Move By Rid 의 **Rb** 칸에 `Bird (Rigidbody)` 가 들어가 있다
- [ ] Play 하면 새가 오른쪽으로 가면서 떨어진다. 중력 코드가 없는데도
- [ ] 스페이스를 누르면 올라갔다가 곡선을 그리며 내려온다
- [ ] Start 에 한 번 쓴 속도로 왜 계속 가는지 말할 수 있다

---

## 안 되면

- **Rb 칸이 `None (Rigidbody)`** → ==아직 아무것도 안 넣었다.== 이 상태로 Play 하면 없는 것에서 꺼내려 해서 에러가 난다. Bird 를 Rb 칸에 끌어다 놓는다.
- **`Keyboard` 에 빨간 줄** → ==새 스크립트에 `using UnityEngine.InputSystem;` 이 없다.== 맨 위에 넣는다.
- **새가 두 배로 빨리 떨어지거나 이상하게 움직인다** → ==Bird Move (Script) 를 안 껐다.== 두 스크립트가 같이 움직이고 있다.

---

## 답 — 이 시간이 끝났을 때의 코드

여기까지 스스로 해봤다면 봐도 된다.

```csharp
using UnityEngine;
using UnityEngine.InputSystem;

public class BirdMoveByRid : MonoBehaviour
{
    public Rigidbody rb;
    public float forwardSpeed = 5;
    public float jumpPower = 10;

    void Start()
    {
        // rb = GetComponent<Rigidbody>();

        // 오른쪽으로움직이는 코드
        rb.linearVelocity = new Vector3(forwardSpeed,0,0);
    }

    // Update is called once per frame
    void Update()
    {
        // 3. 스페이스를 통해 점프
        // 위 방향으로 스페이스를 눌렀을때 점프를 한다.

        if(Keyboard.current.spaceKey.wasPressedThisFrame) // 스페이스를 눌렀을때
        {
            //위 방향으로 점프를 한다.
            rb.linearVelocity = new Vector3(forwardSpeed,jumpPower,0);
        }
    }
}
```

Inspector — Rb 는 `Bird (Rigidbody)`, Jump Power 는 5.

---

<!--
═══════════ 교수용 ═══════════

2차에서 바꾼 것 (ch02 견본 방식)
  - 챕터 제목을 기획서 덩어리로. 절 = 진단(왜 점프 같지 않을까) + 기획서 세 줄을 물리로 다시
  - 기획서 줄 순서를 2 → 1 → 3 으로 바꿨다. 물리로 바꾸면 중력이 제일 쉬워서 (컴포넌트만 붙이면 끝)
  - 「이동 방식」 표는 중력 절 안으로. Rigidbody 를 막 겪은 뒤에 비교한다
  - 오른쪽 절은 「필요한 것 1 새 스크립트 / 2 손에 쥐기 / 3 속도 주기」
  - 점프는 02 의 Translate 점프와 나란히 비교
  - 형광펜 · ▶ Play 표시. 학생 본문에서 영상 시각을 뺐다

수업과 다른 곳
  - 수업 순서: 진단 → 이동 방식 → Rigidbody 추가 → 새 스크립트 → rb · GetComponent · null → Inspector 연결 → 앞으로 → 점프.
    교재는 기획서 줄 단위로 묶었다
  - 21:00 의 rb null 검사 if 는 넣지 않았다 (수업에서 치다가 그만둠)
  - 「한 가지 더」(deltaTime 을 곱한 문제)와 「x 칸에 왜 forwardSpeed」 답은 수업에서 말하지 않은 것. 교재에서 더함
  - 정적 할당 선호 이유 셋 중 「연산도 든다」 는 본문에서 뺐다 (곁가지)
  - 「안 되면」 셋째 줄(BirdMove 를 안 껐다)은 수업에서 실제로 막힌 기록은 없다. 08:45 에 「끄세요」 라고 하신 것에서 뽑았다

시연 순서와 영상 시각 (영상 B)
  00:00 「여기까지 다 됐겠죠?」 → 출석 (00:25–02:23)
  02:23 점프가 잘 안 된다 → 03:38 Scene 뷰에서 jumpPower 10 → 100 → 200 → 300
  04:29 「AI 한테 어떻게 설명할래」 → 05:05 Translate = 순간이동 → 06:00 화면에 펜으로 표시
  06:51 터널링 → 07:00 「가장 쉬운 방법은 Rigidbody」 → 07:42 이동 방식 세 가지 (두 개만 말함)
  08:19 Rigidbody 추가, BirdMove 끄기, Play → 09:26 useGravity 껐다 켜기
  10:22 BirdMoveByRid 생성 (「R I D」 철자 불러 줌)
  11:59 Transform.Translate = Transform 컴포넌트의 기능 → 12:28 Rigidbody 는 대문자 = 클래스
  12:36 public Rigidbody rb; → 13:16 int test 와 비교 → 13:44 기본형은 바로, Rigidbody 는 Start 에서
  14:44 「여기까지 쭉 쳐 보세요」 → 15:19 GetComponent 설명 → 16:02 MeshRenderer·Transform·Collider
  16:28 없으면 null → 17:20 휴지 그림 → 18:34 Rb 칸 None → Play 하면 채워짐
  19:04 동적·정적 할당 → 20:12 Inspector 로 끌어 넣기 → 20:20 「나는 정적 할당을 선호」
  21:00 if (rb == null) 을 치다가 그만둠 → 21:45 「정적 할당으로 갑니다」
  22:08 linearVelocity = (1,0,0) → Update 에도 넣어 봄 → 23:27 Start 로
  23:47 「왜 불편해?」 → 24:11 하드코딩 → forwardSpeed → 24:58 중력은 Rigidbody 가 이미
  25:19 Start 인데 왜 계속 가나 — 속도라서
  26:26 점프 → 27:24 using 추가 → 28:20 linearVelocity = (forwardSpeed, jumpPower, 0)
  28:57 「불편해」 → jumpPower 변수 → 29:32 Play → 29:54 「너무 세다, 5 정도」
  30:19 과제 백업 안내

다음 시간에 짚을 것 (화면에서 본 것)
  - Rigidbody 의 Constraints 를 안 걸었다. 땅에 닿으면 큐브가 굴러가거나 회전할 수 있다
    → Freeze Rotation X·Y·Z, Freeze Position Z
  - x 속도를 Start 에서 한 번만 준다. 땅이나 파이프에 부딪혀 x 속도가 줄면 다시 안 붙는다
  - 카메라가 새를 안 따라간다. 새가 오른쪽으로 가면 곧 화면 밖이다
  - Rigidbody 도 아주 빠르면 터널링이 난다 (Collision Detection: Discrete)

과제 백업 안내 (B 30:19 — 수업 운영이라 학생 본문에서 뺐다)
  - Assets 폴더를 압축해 드라이브에 올린다
  - Bird 를 선택한 화면 스크린샷 하나
  - 제출 양식은 따로 공지
-->
