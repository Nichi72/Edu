# -*- coding: utf-8 -*-
"""수업 채점 봇.

서버 하나 = 수업 하나. 봇을 초대하면 그 서버에 #채점실(선생님 채널)을 만들고 명령을 등록한다. 설정에 서버 ID 는 없다.
학생: 봇 DM 에 제출 zip 을 올린다 → 몇 초 뒤 결과. 봇은 그 학생이 들어 있는 수업 서버를 찾아 그 수업 기준으로 본다.
선생님 (#채점실): /진도 7일차 + 기준 zip, /과녁, /현황, /명단, /다시채점, /등록, /도움

어느 컴에서 켜도 같다 — 기준은 각 서버 #채점실 첨부에서, 명단은 시트에서, 밀린 DM 은 켜질 때 따라잡는다.
실행:  run.bat  (또는 .venv\\Scripts\\python main.py)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import logging.handlers
import queue
import sys

import discord
from discord import app_commands

import settings as cfg
from grader.bundle import Bundle, BundleError
from grader.compare import Comparer, evaluate
from grader.config import load_config
from grader.report import student_message, teacher_detail, teacher_line
from refs import MARK, RefStore, valid_name
from store import Local, Sheet, label, parse_student

log = logging.getLogger("bot")

HELP_STUDENT = (
    "여기에 **제출 zip** 을 올리면 채점한다.\n"
    "zip 은 Unity 메뉴 **제출 ▸ 과제 zip 만들기** 로 만든다. 다른 글은 안 읽는다.\n"
    "봇이 회색(오프라인)이어도 올려 두면 된다. 켜질 때 채점해서 답한다."
)
HELP_TEACHER = (
    "이 서버가 수업 하나다. 기준·과녁·명단·현황은 서버마다 따로다.\n"
    "`/진도 항목 기준` — 오늘 기준 zip 을 올리고 과녁으로 삼는다 (예: 7일차)\n"
    "`/과녁 항목` — 새 기준 없이 과녁만 바꾼다\n"
    "`/현황 [항목]` — 통과 / 미통과 / 미제출 명단\n"
    "`/명단` — 이 수업에 등록된 학생\n"
    "`/다시채점 학생 [자세히]` — 그 학생의 마지막 제출을 지금 기준으로 다시 본다\n"
    "`/등록 학생 학번 이름` — 학번·이름 고치기, 또는 이 수업으로 옮기기\n"
    "학생은 봇 DM 에 zip 을 올리면 된다. 처음 올릴 때 학번과 이름을 묻고, 들어 있는 수업 서버를 찾는다."
)
ASK_NAME = "처음이구나. **학번과 이름**을 띄어서 한 줄로 보내 줘 (예: `20241234 홍길동`). 그다음 바로 채점한다."
WELCOME = (
    "채점 봇이 들어왔다. 이 채널은 **선생님용**이다 (학생에게는 안 보인다).\n"
    "수업 끝에 Unity **제출 ▸ 과제 zip 만들기** → 여기서 `/진도 항목:7일차 기준:(그 zip)`.\n"
    "학생은 봇 DM 에 zip 을 올리면 된다. `/도움` 으로 명령을 본다."
)


class GraderBot(discord.Client):
    def __init__(self, s: cfg.Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        super().__init__(intents=intents)
        self.s = s
        self.tree = app_commands.CommandTree(self)
        self.local = Local(s.data_dir / "bot.db")
        self.comparer = Comparer(load_config())
        self.sheet: Sheet | None = None
        self.sub_dir = s.data_dir / "submissions"
        self.sub_dir.mkdir(exist_ok=True)
        self._refs: dict[int, RefStore] = {}
        self._lock = asyncio.Lock()
        if s.legacy_guild_id:
            self._migrate_legacy(s.legacy_guild_id)
        self._register_commands()

    def _migrate_legacy(self, gid: int) -> None:
        """서버 구분이 없던 때의 data/ 를 .env 의 GUILD_ID 서버 것으로 옮긴다 (한 번만 일어난다)."""
        n = self.local.migrate_legacy(gid)
        old = self.s.data_dir / "refs"
        if old.is_dir():
            new = self.refs_for(gid).dir
            for z in old.glob("*.zip"):
                dst = new / z.name
                if not dst.exists():
                    z.replace(dst)
                    n += 1
            try:
                old.rmdir()
            except OSError:
                pass
        if n:
            log.info("옛 기록 %d건을 서버 %d 것으로 옮겼다", n, gid)

    # ───────────────────────── 수업(서버) 단위 상태 ─────────────────────────
    def refs_for(self, guild_id: int) -> RefStore:
        if guild_id not in self._refs:
            self._refs[guild_id] = RefStore(self.s.data_dir / "guilds" / str(guild_id))
        return self._refs[guild_id]

    def target_of(self, guild_id: int) -> str | None:
        return self.local.get(f"target:{guild_id}")

    def set_target(self, guild_id: int, cp: str | None) -> None:
        self.local.set(f"target:{guild_id}", cp)

    def grading_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """이 서버의 #채점실: 이름이 같은 텍스트 채널 (옛 설정의 GRADING_CHANNEL_ID 도 인정)."""
        for c in guild.text_channels:
            if c.id == self.s.grading_channel_id or c.name == self.s.grading_channel:
                return c
        return None

    def class_guilds(self) -> list[discord.Guild]:
        """#채점실이 있는 서버 = 수업."""
        return [g for g in self.guilds if self.grading_channel(g)]

    # ───────────────────────── 시작 ─────────────────────────
    async def setup_hook(self) -> None:
        await self._open_sheet()

    async def on_ready(self) -> None:
        log.info("로그인 %s · 인스턴스 %s", self.user, self.s.instance)
        if await self._another_instance_alive():
            log.error("다른 컴에서 이미 봇이 돌고 있다. 이쪽은 끈다 (2분 지나도 그러면 저쪽이 죽은 것이니 다시 켠다)")
            await self.close()
            return
        for g in self.guilds:
            await self._setup_guild(g)
        await self._restore_roster()
        self.loop.create_task(self._heartbeat_loop())
        self.loop.create_task(self._outbox_loop())
        self.loop.create_task(self._catch_up())
        classes = [f"{g.name}(과녁 {self.target_of(g.id) or '없음'})" for g in self.class_guilds()]
        log.info("준비 끝 · 수업 %d개: %s", len(classes), ", ".join(classes) or "없음 — 서버에 초대하면 바로 붙는다")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("새 서버에 들어갔다: %s", guild.name)
        await self._setup_guild(guild, announce=True)

    async def _setup_guild(self, guild: discord.Guild, announce: bool = False) -> None:
        """명령 등록 + #채점실 확보 + 기준 복원. 초대만 하면 되게."""
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        except discord.HTTPException as e:
            log.warning("%s: 명령 등록 실패 (초대 링크에 applications.commands 가 있었나?): %s", guild.name, e)
        ch = self.grading_channel(guild)
        if ch is None:
            ch = await self._create_grading_channel(guild)
            if ch is None:
                return
            announce = True
        if announce:
            try:
                await ch.send(WELCOME)
            except discord.HTTPException:
                pass
        await self._restore_refs(guild, ch)

    async def _create_grading_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                  read_message_history=True, attach_files=True),
        }
        try:
            ch = await guild.create_text_channel(self.s.grading_channel, overwrites=overwrites,
                                                 reason="채점 봇 선생님 채널")
            log.info("%s: #%s 채널을 만들었다 (관리자에게만 보인다)", guild.name, ch.name)
            return ch
        except discord.Forbidden:
            log.error("%s: #%s 채널이 없고 만들 권한도 없다. 채널을 직접 만들어 봇을 넣거나, 초대 링크로 다시 초대해 "
                      "'채널 관리' 권한을 준다", guild.name, self.s.grading_channel)
        except discord.HTTPException as e:
            log.error("%s: #%s 채널을 못 만들었다: %s", guild.name, self.s.grading_channel, e)
        return None

    async def _open_sheet(self) -> None:
        if not (self.s.sheet_id and self.s.google_sa_json):
            log.warning("시트 설정이 없어 로컬 기록만 한다 (SHEET_ID / GOOGLE_SA_JSON)")
            return
        try:
            self.sheet = await asyncio.to_thread(Sheet, self.s.sheet_id, self.s.google_sa_json)
            log.info("시트 연결 됨")
        except Exception as e:           # 시트가 죽어도 봇은 산다
            log.warning("시트 연결 실패, 로컬 기록만: %s", e)

    async def _another_instance_alive(self) -> bool:
        if not self.sheet:
            return False
        try:
            hb = await asyncio.to_thread(self.sheet.read_heartbeat)
        except Exception as e:
            log.warning("심장박동을 못 읽었다 (%s). 그냥 켠다", e)
            return False
        now = dt.datetime.now(dt.timezone.utc)
        return hb.alive(now) and hb.instance != self.s.instance

    async def _restore_refs(self, guild: discord.Guild, ch: discord.TextChannel) -> None:
        """그 서버 #채점실의 [기준] 메시지에서 없는 기준을 내려받고, 과녁이 비어 있으면 가장 최근 것으로."""
        refs = self.refs_for(guild.id)
        latest: str | None = None
        try:
            async for m in ch.history(limit=500):
                if m.author.id != self.user.id or not m.attachments:
                    continue
                cp = RefStore.parse_mark(m.content)
                if not cp:
                    continue
                if latest is None:
                    latest = cp
                if not refs.has(cp):
                    try:
                        refs.save(cp, await m.attachments[0].read())
                        log.info("%s: 기준 %s 를 #%s 에서 복원", guild.name, cp, ch.name)
                    except (BundleError, discord.HTTPException) as e:
                        log.warning("%s: 기준 %s 복원 실패: %s", guild.name, cp, e)
        except discord.Forbidden:
            log.error("%s: #%s 기록을 읽을 권한이 없다. 봇에 '메시지 기록 보기' 권한을 준다", guild.name, ch.name)
        if not self.target_of(guild.id) and latest and refs.has(latest):
            self.set_target(guild.id, latest)

    async def _restore_roster(self) -> None:
        if not self.sheet:
            return
        try:
            for uid, sid, name, when, gid in await asyncio.to_thread(self.sheet.read_roster):
                if not self.local.name_of(uid):
                    self.local.register(uid, sid, name, gid, when or None)
        except Exception as e:
            log.warning("명단 복원 실패: %s", e)

    # ───────────────────────── 배경 작업 ─────────────────────────
    async def _heartbeat_loop(self) -> None:
        while not self.is_closed():
            if self.sheet:
                try:
                    await asyncio.to_thread(self.sheet.heartbeat, self.s.instance)
                except Exception as e:
                    log.debug("심장박동 실패: %s", e)
            await asyncio.sleep(30)

    async def _outbox_loop(self) -> None:
        while not self.is_closed():
            await self._flush_outbox()
            await asyncio.sleep(60)

    async def _flush_outbox(self) -> None:
        if not self.sheet:
            return
        done = []
        for r in self.local.outbox():
            try:
                await asyncio.to_thread(self.sheet.append, r["kind"], json.loads(r["payload"]))
                done.append(r["id"])
            except Exception as e:
                log.debug("시트 올리기 실패, 나중에: %s", e)
                break
        if done:
            self.local.dequeue(done)

    async def _catch_up(self) -> None:
        """꺼져 있던 동안 명단 학생이 보낸 DM 의 zip 을 채점한다.

        디스코드는 봇에게 DM 목록을 주지 않는다. 그래서 명단에 있는 학생만 여기서 찾고,
        명단에 없는 학생은 다음에 아무 글이나 보내는 순간 on_message 가 그 DM 을 거슬러 본다.
        """
        n = 0
        for row in self.local.roster():
            try:
                user = self.get_user(row["user_id"]) or await self.fetch_user(row["user_id"])
                dm = user.dm_channel or await user.create_dm()
                n += await self._scan_dm(dm, user)
            except discord.HTTPException as e:
                log.warning("따라잡기 실패 %s: %s", row["name"], e)
        if n:
            log.info("밀린 제출 %d건을 채점했다", n)

    async def _scan_dm(self, channel: discord.DMChannel, user: discord.abc.User) -> int:
        """이 DM 에서 아직 안 본 zip 을 오래된 것부터 채점한다. 답장은 마지막 것에만. 처리한 수를 돌려준다."""
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=self.s.catchup_days)
        msgs: list[discord.Message] = []
        async for m in channel.history(after=since, oldest_first=True, limit=200):
            if m.author.id != self.user.id and _zip_of(m) and not self.local.seen(m.id):
                msgs.append(m)
        if not msgs:
            return 0
        if not self.local.name_of(user.id):
            self.local.set(f"pending:{user.id}", "1")
            await channel.send(ASK_NAME)
            return 0
        for i, m in enumerate(msgs):
            last = i == len(msgs) - 1
            note = f"밀린 제출 {len(msgs)}건 중 마지막" if last and len(msgs) > 1 else ("밀린 제출" if last else "")
            await self.handle_submission(m, reply=last, note=note)
        self.local.set(f"last_msg:{user.id}", str(msgs[-1].id))
        return len(msgs)

    # ───────────────────────── 학생이 어느 수업인지 ─────────────────────────
    async def _classes_of(self, user: discord.abc.User) -> list[discord.Guild]:
        """학생이 들어 있는 수업 서버들 (#채점실이 있는 서버만)."""
        found = []
        for g in self.class_guilds():
            m = g.get_member(user.id)
            if m is None:
                try:
                    m = await g.fetch_member(user.id)
                except discord.NotFound:
                    continue
                except discord.HTTPException as e:
                    log.debug("%s 멤버 조회 실패: %s", g.name, e)
                    continue
            found.append(g)
        return found

    async def _resolve_class(self, channel: discord.abc.Messageable, user: discord.abc.User,
                             sid: str, name: str) -> int | None:
        """수업을 정해 등록까지 마친다. 못 정하면 학생에게 묻고 None."""
        gs = await self._classes_of(user)
        if len(gs) == 1:
            self._register(user.id, sid, name, gs[0])
            return gs[0].id
        if not gs:
            self.local.set(f"pending:{user.id}", json.dumps({"sid": sid, "name": name}, ensure_ascii=False))
            await channel.send("아직 **수업 서버**에 들어와 있지 않다. 선생님이 준 초대 링크로 서버에 들어온 뒤, "
                               "여기에 아무 글이나 보내 줘.")
            return None
        self.local.set(f"pending:{user.id}", json.dumps({"sid": sid, "name": name, "choices": [g.id for g in gs]},
                                                        ensure_ascii=False))
        lines = [f"{i + 1}. {g.name}" for i, g in enumerate(gs)]
        await channel.send("수업 서버가 여러 개다. **몇 번째 수업**인지 번호로 보내 줘.\n" + "\n".join(lines))
        return None

    def _register(self, uid: int, sid: str, name: str, guild: discord.Guild) -> None:
        self.local.register(uid, sid, name, guild.id)
        self.local.set(f"pending:{uid}", None)
        self.local.enqueue("roster", [uid, guild.name, sid, name, dt.datetime.now().isoformat(timespec="seconds"),
                                      guild.id])

    # ───────────────────────── DM ─────────────────────────
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return
        uid = message.author.id
        first_contact = self.local.get(f"last_msg:{uid}") is None
        self.local.set(f"last_msg:{uid}", str(message.id))

        # 봇이 아는 학생이 zip 을 올렸다 → 바로 채점. (밀린 것은 켜질 때 이미 따라잡았다)
        if _zip_of(message) and not first_contact and self.local.name_of(uid):
            await self.handle_submission(message)
            return
        # 등록 중인 학생의 학번·이름 / 수업 선택
        if self.local.get(f"pending:{uid}") and not message.attachments:
            if await self._continue_registration(message):
                return
        # 그 밖의 모든 경우 — 첫 접촉, 글, 엉뚱한 첨부: 이 DM 을 거슬러 밀린 zip 이 있는지 본다 (지금 메시지 포함)
        if await self._scan_dm(message.channel, message.author) or self.local.get(f"pending:{uid}"):
            return
        if message.attachments:
            await message.channel.send("zip 만 받는다. Unity 메뉴 **제출 ▸ 과제 zip 만들기** 로 만든 파일을 올린다.")
            return
        await message.channel.send(HELP_STUDENT)

    async def _continue_registration(self, message: discord.Message) -> bool:
        """pending 상태를 한 단계 진행한다. 등록이 끝났으면 밀린 zip 을 채점한다. 처리했으면 True."""
        uid = message.author.id
        state = self.local.get(f"pending:{uid}") or ""
        text = message.content.strip()
        if state.startswith("{"):                      # 학번·이름은 받았고 수업을 정하는 중
            d = json.loads(state)
            choices = d.get("choices")
            if choices:
                if not text.isdigit() or not (1 <= int(text) <= len(choices)):
                    await message.channel.send(f"1 부터 {len(choices)} 사이 번호로 보내 줘.")
                    return True
                guild = self.get_guild(choices[int(text) - 1])
                if guild is None:
                    if await self._resolve_class(message.channel, message.author, d["sid"], d["name"]) is None:
                        return True
                else:
                    self._register(uid, d["sid"], d["name"], guild)
            else:                                      # 서버에 들어왔는지 다시 본다
                if await self._resolve_class(message.channel, message.author, d["sid"], d["name"]) is None:
                    return True
        else:                                          # 학번·이름을 기다리는 중
            if not text:
                return False
            parsed = parse_student(text)
            if not parsed:
                await message.channel.send("**학번과 이름을 둘 다** 띄어서 한 줄로 보내 줘 (예: `20241234 홍길동`).")
                return True
            if await self._resolve_class(message.channel, message.author, *parsed) is None:
                return True
        st = self.local.student(uid)
        guild = self.get_guild(st["guild_id"])
        await message.channel.send(f"**{label(st['sid'], st['name'])}** · {guild.name if guild else '?'} 수업으로 등록했다. "
                                   "올려 둔 zip 을 채점한다.")
        if not await self._scan_dm(message.channel, message.author):
            await message.channel.send("올린 zip 을 못 찾겠다. 다시 올려 줘.")
        return True

    async def handle_submission(self, message: discord.Message, reply: bool = True, note: str = "") -> None:
        att = _zip_of(message)
        user = message.author
        st = self.local.student(user.id)
        if not st:
            self.local.set(f"pending:{user.id}", "1")
            await message.channel.send(ASK_NAME)
            return
        sid, name = st["sid"] or "", st["name"]
        who = label(sid, name)
        gid = st["guild_id"]
        if not gid or self.get_guild(gid) is None:     # 옛 명단이거나 봇이 그 서버에서 나갔다
            gid = await self._resolve_class(message.channel, user, sid, name)
            if gid is None:
                return
        guild = self.get_guild(gid)
        if att.size > self.s.max_attachment:
            await message.channel.send(f"파일이 너무 크다 ({att.size // 1024 // 1024} MB). Library 폴더가 섞인 것 같다. 제출 버튼으로 다시 만든다.")
            return
        async with self._lock:
            try:
                data = await att.read()
                sub = Bundle.from_zip_bytes(data, att.filename)
            except BundleError as e:
                await message.channel.send(f"읽을 수 없다: {e}")
                return
            except discord.HTTPException as e:
                await message.channel.send(f"파일을 내려받지 못했다 ({e}). 다시 올려 줘.")
                return

            target = self.target_of(gid)
            p = evaluate(self.refs_for(gid).all(), sub, self.comparer, target)
            nth = self.local.count(user.id, target) + 1
            when = (message.created_at.astimezone()).strftime("%m/%d %H:%M")
            fname = f"{user.id}_{message.id}.zip"
            (self.sub_dir / fname).write_bytes(data)
            tr = p.target_result
            summary = "; ".join(f.student for f in tr.findings[:4]) if tr and not tr.ok else ""
            self.local.add_submission(
                message_id=message.id, user_id=user.id, sid=sid, name=name, guild_id=gid, at=when,
                target=target or "", ok=int(p.target_ok), reached=p.reached or "", summary=summary, nth=nth,
                file=fname, device=str(sub.manifest.get("device", "")), detail=teacher_detail(p))
            self.local.enqueue("submission", [when, guild.name, sid, name, user.id, target or "",
                                              "통과" if p.target_ok else "미통과", p.reached or "", summary, nth,
                                              att.filename, sub.manifest.get("device", ""), message.id, gid])

        if not reply:                      # 밀린 제출 여러 건 중 앞의 것: 기록만 하고 조용히
            return
        try:
            await message.channel.send(student_message(p, nth=nth, when=when))
        except discord.HTTPException as e:
            log.warning("DM 답장 실패 %s: %s", who, e)
        await self._teacher_log(guild, teacher_line(who, p, nth=nth, when=when) + (f" · ({note})" if note else ""))

    async def _teacher_log(self, guild: discord.Guild, text: str) -> None:
        ch = self.grading_channel(guild)
        if ch:
            try:
                await ch.send(text)
            except discord.HTTPException as e:
                log.warning("%s: #%s 알림 실패: %s", guild.name, ch.name, e)

    # ───────────────────────── 슬래시 명령 ─────────────────────────
    def _is_teacher(self, it: discord.Interaction) -> bool:
        if it.guild is None:
            return False
        ch = self.grading_channel(it.guild)
        if ch is None or it.channel_id != ch.id:
            return False
        return not self.s.teacher_ids or it.user.id in self.s.teacher_ids

    def _register_commands(self) -> None:
        bot = self

        async def guard(it: discord.Interaction) -> bool:
            lag = (discord.utils.utcnow() - it.created_at).total_seconds()
            if lag > 1.5:
                log.warning("명령 /%s 이(가) %.1f초 늦게 도착했다 — 봇 창이 멈춰 있었나? (창 안을 클릭하면 멈춘다. Esc 로 푼다)",
                            it.command.name if it.command else "?", lag)
            if bot._is_teacher(it):
                return True
            await it.response.send_message(f"이 명령은 #{bot.s.grading_channel} 에서 선생님만 쓴다.", ephemeral=True)
            return False

        async def ack(it: discord.Interaction) -> bool:
            """3초 안에 '생각 중' 표시. 못 하면 False — 그래도 일은 계속하고 결과는 채널에 올린다."""
            try:
                await it.response.defer(ephemeral=True, thinking=True)
                return True
            except discord.NotFound:
                log.error("/%s 응답 시간(3초)을 놓쳤다. 일은 계속한다. 봇 창 안을 클릭해 멈춰 있지 않았는지 확인한다",
                          it.command.name if it.command else "?")
                return False

        async def say(it: discord.Interaction, alive: bool, text: str) -> None:
            if alive:
                await it.followup.send(text, ephemeral=True)
            else:
                await it.channel.send(text)

        @self.tree.command(name="진도", description="오늘 기준 zip 을 올리고 과녁으로 삼는다 (예: 7일차)")
        @app_commands.describe(항목="오늘 항목 이름 (예: 7일차, 과제1). 숫자가 들어가면 순서를 안다", 기준="선생님 프로젝트에서 제출 버튼으로 만든 zip")
        async def jindo(it: discord.Interaction, 항목: str, 기준: discord.Attachment):
            if not await guard(it):
                return
            cp = 항목.strip().lower()
            if not valid_name(cp):
                await it.response.send_message('항목 이름에 공백이나 / \\ : * ? " < > | 는 못 쓴다 (30자 이하).', ephemeral=True)
                return
            alive = await ack(it)
            refs = bot.refs_for(it.guild.id)
            try:
                data = await 기준.read()
                b = refs.save(cp, data)
            except (BundleError, discord.HTTPException) as e:
                await say(it, alive, f"기준으로 못 쓴다: {e}")
                return
            bot.set_target(it.guild.id, cp)
            stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            await it.channel.send(f"{MARK} {cp} · {stamp} · {b.summary()}",
                                  file=discord.File(refs.dir / f"{cp}.zip", filename=f"{cp}.zip"))
            classes = [p.split("/")[-1] for p in b.scripts()]
            await say(it, alive, f"기준 **{cp}** 저장, 과녁으로 삼았다.\n스크립트: {', '.join(classes) or '없음'}\n"
                                 f"이 수업의 기준 목록: {', '.join(refs.names())}")

        @self.tree.command(name="과녁", description="새 기준 없이 과녁만 바꾼다")
        async def target_cmd(it: discord.Interaction, 항목: str):
            if not await guard(it):
                return
            cp = 항목.strip().lower()
            refs = bot.refs_for(it.guild.id)
            if not refs.has(cp):
                await it.response.send_message(f"{cp} 기준이 없다. 있는 것: {', '.join(refs.names()) or '없음'}", ephemeral=True)
                return
            bot.set_target(it.guild.id, cp)
            await it.response.send_message(f"과녁을 **{cp}** 로 바꿨다.")

        @self.tree.command(name="현황", description="통과 / 미통과 / 미제출 명단")
        async def status_cmd(it: discord.Interaction, 항목: str | None = None):
            if not await guard(it):
                return
            gid = it.guild.id
            cp = (항목 or bot.target_of(gid) or "").strip().lower()
            if not cp:
                await it.response.send_message("과녁이 없다. /진도 로 기준을 올린다.", ephemeral=True)
                return
            rows = bot.local.status(gid, cp)
            roster = bot.local.roster(gid)
            who = {r["user_id"]: label(r["sid"], r["name"]) for r in roster}
            ok = [(who[r["user_id"]], rows[r["user_id"]]) for r in roster if r["user_id"] in rows and rows[r["user_id"]]["ok"]]
            bad = [(who[r["user_id"]], rows[r["user_id"]]) for r in roster if r["user_id"] in rows and not rows[r["user_id"]]["ok"]]
            none = [who[r["user_id"]] for r in roster if r["user_id"] not in rows]
            lines = [f"**{it.guild.name} · {cp} 현황** (등록 {len(roster)}명) — 통과 {len(ok)} · 미통과 {len(bad)} · 미제출 {len(none)}"]
            if bad:
                lines.append("미통과")
                lines += [f"  {n}  {r['nth']}회  {r['summary'] or '-'}" for n, r in bad]
            if none:
                lines.append("미제출: " + ", ".join(none))
            if ok:
                lines.append("통과: " + ", ".join(n for n, _ in ok))
            await it.response.send_message(_clip("\n".join(lines)))

        @self.tree.command(name="명단", description="이 수업에 등록된 학생")
        async def roster_cmd(it: discord.Interaction):
            if not await guard(it):
                return
            roster = bot.local.roster(it.guild.id)
            if not roster:
                await it.response.send_message("이 수업에 아직 등록된 학생이 없다.", ephemeral=True)
                return
            lines = [f"{label(r['sid'], r['name'])}  <@{r['user_id']}>  (등록 {r['registered_at'][:10]})" for r in roster]
            await it.response.send_message(_clip(f"{it.guild.name} · 등록 {len(roster)}명\n" + "\n".join(lines)),
                                           allowed_mentions=discord.AllowedMentions.none())

        @self.tree.command(name="다시채점", description="학생의 마지막 제출을 지금 기준으로 다시 본다")
        async def regrade_cmd(it: discord.Interaction, 학생: discord.User, 자세히: bool = False):
            if not await guard(it):
                return
            row = bot.local.latest(학생.id)
            if not row:
                await it.response.send_message("그 학생의 제출이 없다.", ephemeral=True)
                return
            path = bot.sub_dir / row["file"]
            if not path.exists():
                await it.response.send_message("이 컴에는 그 zip 이 없다 (다른 컴에서 받은 제출). 그 컴에서 하거나 학생에게 다시 올리라고 한다.", ephemeral=True)
                return
            alive = await ack(it)
            gid = it.guild.id
            sub = Bundle.from_path(path)
            p = evaluate(bot.refs_for(gid).all(), sub, bot.comparer, bot.target_of(gid))
            text = f"**{label(row['sid'], row['name'])}** · {row['at']} 제출 · 과녁 {bot.target_of(gid)}\n"
            text += teacher_detail(p) if 자세히 else student_message(p, nth=row["nth"], when=row["at"])
            await say(it, alive, _clip(text))

        @self.tree.command(name="등록", description="학생의 학번·이름 고치기, 또는 이 수업으로 등록")
        async def register_cmd(it: discord.Interaction, 학생: discord.User, 학번: str, 이름: str):
            if not await guard(it):
                return
            sid, name = " ".join(학번.split())[:20], " ".join(이름.split())[:20]
            if not sid or not name:
                await it.response.send_message("학번과 이름을 둘 다 적는다.", ephemeral=True)
                return
            bot._register(학생.id, sid, name, it.guild)
            await it.response.send_message(f"<@{학생.id}> → **{label(sid, name)}** ({it.guild.name})",
                                           allowed_mentions=discord.AllowedMentions.none())

        @self.tree.command(name="도움", description="봇 사용법")
        async def help_cmd(it: discord.Interaction):
            await it.response.send_message(HELP_TEACHER if bot._is_teacher(it) else HELP_STUDENT, ephemeral=True)

        @self.tree.error
        async def on_command_error(it: discord.Interaction, error: app_commands.AppCommandError) -> None:
            cause = getattr(error, "original", error)
            name = it.command.name if it.command else "?"
            if isinstance(cause, discord.NotFound) and cause.code == 10062:
                lag = (discord.utils.utcnow() - it.created_at).total_seconds()
                log.error("/%s 응답 시간(3초)을 놓쳤다 (명령 뒤 %.1f초). 봇 창 안을 클릭하면 봇이 멈춘다 — Esc 를 누르고 다시 명령한다",
                          name, lag)
                return
            log.error("/%s 처리 중 오류: %s", name, cause, exc_info=cause)


def _zip_of(message: discord.Message) -> discord.Attachment | None:
    return next((a for a in message.attachments if a.filename.lower().endswith(".zip")), None)


def _clip(s: str, limit: int = 1900) -> str:
    return s if len(s) <= limit else s[:limit - 10] + "\n… (잘림)"


def _unfreeze_console() -> None:
    """Windows 콘솔은 창 안을 클릭하면 '선택 모드'가 되어 출력이 막히고 프로그램이 통째로 멈춘다.
    QuickEdit 를 꺼서 클릭으로는 안 멈추게 한다 (드래그 선택도 안 되지만 로그는 bot.log 에 있다)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-10)                      # STD_INPUT_HANDLE
        mode = ctypes.c_uint()
        if k32.GetConsoleMode(h, ctypes.byref(mode)):
            k32.SetConsoleMode(h, (mode.value | 0x80) & ~0x40)   # ENABLE_EXTENDED_FLAGS 켜고 QUICK_EDIT 끔
    except Exception:
        pass


def main() -> None:
    s = cfg.load()
    _unfreeze_console()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # 콘솔 쓰기는 별도 스레드가 맡는다 — 창이 멈춰도 봇의 이벤트 루프는 안 멈춘다
    q: queue.SimpleQueue = queue.SimpleQueue()
    listener = logging.handlers.QueueListener(q, logging.StreamHandler(sys.stdout))
    listener.start()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.handlers.QueueHandler(q),
                                  logging.FileHandler(s.data_dir / "bot.log", encoding="utf-8")])
    logging.getLogger("discord").setLevel(logging.WARNING)
    try:
        GraderBot(s).run(s.token, log_handler=None)
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
