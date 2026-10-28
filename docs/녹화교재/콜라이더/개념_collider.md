# 충돌 정리 — Collider 를 더 알고 싶으면

<!--
상태:     초안 (2026-10-28). 강사 검토 전
파일:     Assets/Script/BirdMoveByRid.cs
돌아가기: ch04
재료:     유튜브 V1 (더블엘) · V2 (베르) · V3 (베르, 레이어) — 04 · 05 에서 쓰지 않은 부분
-->

04 · 05 에서 Collider 로 게임 오버와 점수를 만들었다. 여기서는 그때 「이런 게 있다」 로 넘어간 것들을 본다. ==04 · 05 를 끝내는 데 꼭 필요하지는 않다.== 다른 게임을 만들 때 다시 펼쳐 본다.

---

## Collider 의 모양

| 컴포넌트 | 모양 | 크기를 정하는 칸 | 주로 |
|---|---|---|---|
| Box Collider | 상자 | Size (x · y · z) | 벽 · 바닥 · 상자 |
| Sphere Collider | 공 | Radius (반지름) | 공 · 동그란 물체 |
| Capsule Collider | 캡슐 | Radius (두께) · Height (길이) · Direction (길어지는 축) | 사람 캐릭터 |
| Mesh Collider | 모델 모양 그대로 | — | 꼭 필요할 때만 |

- **Center** — 범위의 중심을 옮긴다. 모델은 그대로 두고 초록 선만 움직인다
- **Edit Collider** 버튼 — 누르면 Scene 뷰의 초록 선에 점이 생긴다. 끌어서 크기를 바꾼다
- ==Mesh Collider 는 정확하지만 무겁다.== 보통은 Box · Sphere · Capsule 을 하나 또는 여러 개 붙여 비슷하게 맞춘다
- 2D 게임은 이름에 2D 가 붙은 것을 쓴다. Box Collider 2D, Circle Collider 2D. ==3D 와 2D 는 서로 부딪히지 않는다.==

씬 전체의 Collider 를 한 번에 보려면 **Window > Analysis > Physics Debugger.** Collider 가 있는 곳이 모두 칠해진다.

---

## Enter · Stay · Exit

04 · 05 에서는 Enter 만 썼다. 함수는 모두 여섯 개다.

| | 벽 (Is Trigger 끔) | 결승선 (Is Trigger 켬) |
|---|---|---|
| 닿는 순간 한 번 | `OnCollisionEnter(Collision collision)` | `OnTriggerEnter(Collider other)` |
| 닿아 있는 동안 계속 | `OnCollisionStay(Collision collision)` | `OnTriggerStay(Collider other)` |
| 떨어지는 순간 한 번 | `OnCollisionExit(Collision collision)` | `OnTriggerExit(Collider other)` |

==처음엔 여섯 개에 `Debug.Log` 를 하나씩 넣고 Play 해 보면 언제 불리는지 바로 보인다.==

**Stay 가 안 찍힐 때** — 물체가 완전히 멈추면 Rigidbody 가 「잠든다」. 잠든 동안은 닿아 있어도 Stay 가 불리지 않는다. 다시 움직이면 깨어난다.

Enter 와 Exit 를 짝으로 쓰는 예 — 물웅덩이 Trigger 에 들어가면(Enter) 느려지고, 나오면(Exit) 원래 속도로.

---

## 부딪힘을 알려면

==둘 다 Collider 가 있고, 둘 중 하나에는 Rigidbody 가 있어야 한다.==

| 새 | 상대 | 알 수 있나 |
|---|---|---|
| Collider + Rigidbody | Collider | 안다 — 04 의 새와 파이프 |
| Collider | Collider | 모른다. 둘 다 Rigidbody 가 없다 |
| Rigidbody 만 | Collider | 모른다. 새가 그냥 뚫고 지나간다 |

Rigidbody 는 움직이는 쪽에 붙인다. 함수는 부딪힌 **두 쪽 어디에** 써도 불린다. 04 에서는 새에 썼지만 파이프 쪽 스크립트에 써도 된다.

둘 다 Rigidbody 가 있으면 서로 민다. 새가 상자를 밀고 가는 게임이라면 상자에도 Rigidbody 를 붙인다.

---

## 무엇과 부딪혔는지 알기

04 에서는 땅이든 파이프든 똑같이 게임 오버였다. 그래서 상대를 볼 필요가 없었다. ==상대에 따라 다른 일을 해야 하면 괄호 안을 쓴다.==

| 쓰는 것 | 뜻 |
|---|---|
| `collision.gameObject` / `other.gameObject` | 부딪힌 상대 오브젝트 |
| `.name` | 상대의 이름 |
| `.CompareTag("Ground")` | 상대의 Tag 가 Ground 인가 (bool) |
| `.GetComponent<Rigidbody>()` | 상대에게 붙은 컴포넌트. 03 의 GetComponent 에 「누구의」 가 붙었다 |

**Tag** 는 오브젝트에 붙이는 이름표다. Inspector 맨 위 **Tag** → **Add Tag...** → `+` 로 만들고, 오브젝트를 골라 지정한다.

예: 땅에 떨어졌을 때만 다른 말을 찍는다.

```csharp
    void OnCollisionEnter(Collision collision)
    {
        if(collision.gameObject.CompareTag("Ground"))
        {
            Debug.Log("땅에 떨어졌다");
        }

        Debug.Log("게임 오버");
        Time.timeScale = 0;
    }
```

==Tag 이름도 철자 · 대소문자까지 같아야 한다.== `CompareTag` 는 만들지 않은 Tag 이름을 넣으면 Console 에 에러로 알려 준다.

---

## 레이어로 아예 안 부딪히게

총알끼리 부딪히면 안 되는 게임을 생각해 보자. 코드에 「총알이면 무시」 를 쓸 수 있다. 그런데 무시할 짝이 늘어날수록 하나씩 빠뜨린다. 적이 회복 아이템을 먹어 버리는 식의 버그가 난다.

==레이어로 묶고, 레이어끼리 부딪힐지를 한 표에서 정한다.==

1. Inspector 맨 위 **Layer** → **Add Layer...** → 빈 칸에 이름 (예: `Bullet`)
2. 오브젝트를 골라 Layer 를 `Bullet` 으로
3. **Edit > Project Settings > Physics** → **Layer Collision Matrix**
4. `Bullet` 줄과 `Bullet` 칸이 만나는 체크를 끈다

체크를 끄면 그 두 레이어는 ==아예 부딪히지 않는다. 함수도 불리지 않는다.== 코드는 한 줄도 안 바뀐다.

레이어 칸 수는 정해져 있고, 앞쪽 몇 칸은 Unity 가 쓴다. 필요할 때만 만든다.

---

## Physics Material — 미끄러짐과 튕김

부딪혔을 때 얼마나 미끄러지고 얼마나 튈지를 정한다. Project 창 오른쪽 클릭 → **Create > Physics Material** 로 만들고, Collider 의 **Material** 칸에 넣는다.

| 칸 | 뜻 | 0 이면 | 1 이면 |
|---|---|---|---|
| Dynamic Friction | 움직이는 중의 마찰 | 얼음처럼 미끄러진다 | 금방 멈춘다 |
| Static Friction | 멈춰 있을 때의 마찰 | 살짝 밀어도 미끄러진다 | 잘 안 밀린다 |
| Bounciness | 튕기는 정도 | 안 튄다 | 거의 줄지 않고 튄다 |

두 물체의 값이 다를 때 어떻게 합칠지는 **Friction Combine** · **Bounce Combine** 이 정한다. Average(평균) · Minimum(작은 쪽) · Multiply(곱) · Maximum(큰 쪽).

예: 고무공. Bounciness 0.8, Bounce Combine Maximum. 바닥 재질이 뭐든 공이 통통 튄다.

<!--
═══════════ 교수용 ═══════════

이 페이지에 모은 것 — 영상 셋에서 04 · 05 에 쓰지 않은 것 전부
  - Collider 모양 · Center · Size · Radius · Height · Direction · Edit Collider (V1 00:21–02:54 · V2 00:37–03:03)
  - Mesh Collider 는 무겁다, 2D 는 따로 (V1 00:29–01:02)
  - Physics Debug(ger) 창 (V1 01:45)
  - Enter · Stay · Exit (V1 05:35–06:35 · V2 05:41–06:51). Stay 가 안 찍히는 이유(잠듦)는 영상에서 말하지 않았다. 여기서 더함
  - 둘 중 하나는 Rigidbody, 함수는 어느 쪽에 써도 된다 (V2 08:18–09:17. V2 는 스크립트를 Cube 에, Rigidbody 는 Sphere 에 붙였다)
  - 둘 다 Rigidbody 면 민다 (V1 06:50)
  - collision.gameObject · CompareTag · GetComponent (V1 07:09–09:21 · V2 09:17–09:52). V1 의 Water · Monster HP 예제는 쓰지 않고 Ground Tag 예로 바꿨다
  - 레이어 충돌 매트릭스 (V3 전체). 총알 · 힐팩 · 던전 트리거 예는 V3 02:04 에서 가져와 짧게 줄였다
  - Physics Material (V1 09:26–11:11 · V2 04:24–05:15)

확인할 것 (Unity 6.3)
  - Physics Debugger 메뉴 위치와 이름 (V1 은 2022.3 의 Physics Debug)
  - Create 메뉴의 Physics Material 이름 (옛 이름 Physic Material)
  - Project Settings > Physics 에서 Layer Collision Matrix 의 위치 (6.x 에서 Physics 설정이 여러 탭으로 나뉘었다)
  - V3 의 「사용자 레이어 24개」 는 옛 버전 기준이라 숫자를 쓰지 않았다
-->
