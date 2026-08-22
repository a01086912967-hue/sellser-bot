import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import os
import uuid
from datetime import datetime, timedelta

# ==========================================
# 1. 설정 및 ID 상수
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")

CATEGORY_ID = 1457078078294458390       # 티켓 카테고리 ID
ADMIN_ROLE_ID = 1458178323434836199     # 관리자 역할 ID
LOG_CHANNEL_ID = 1540722623883911250    # 로그 채널 ID
ADMIN_PANEL_CHANNEL_ID = 1540725362776871034  # 관리자 제어 패널 채널 ID
LICENSE_ROLE_ID = 1540733768275333270   # 라이센스 보유자 역할 ID
IMAGE_FILE_NAME = "guide.png"           # 안내 이미지 파일명

PASTEL_PINK = 0xFFB6C1

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

license_db = {}
user_licenses = {}

async def send_log(guild: discord.Guild, embed: discord.Embed):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)


# ==========================================
# 2. UI 컴포넌트 & 모달
# ==========================================

class LicenseRegisterModal(discord.ui.Modal, title="🔑 라이센스 코드 등록"):
    license_code = discord.ui.TextInput(
        label="발급받은 라이센스 코드를 입력하세요",
        placeholder="KEY-XXXXXXXXXXXX",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        code = self.license_code.value.strip()

        if code not in license_db:
            await interaction.followup.send("❌ 유효하지 않은 라이센스 코드입니다.", ephemeral=True)
            return

        lic_info = license_db[code]
        if lic_info["used"]:
            await interaction.followup.send("❌ 이미 사용된 라이센스 코드입니다.", ephemeral=True)
            return

        days = lic_info["days"]
        expire_time = datetime.now() + timedelta(days=days)
        lic_info["used"] = True
        lic_info["user_id"] = interaction.user.id
        lic_info["expires_at"] = expire_time

        user_licenses[interaction.user.id] = {
            "guild_id": interaction.guild.id,
            "code": code,
            "expires_at": expire_time
        }

        role = interaction.guild.get_role(LICENSE_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)

        embed = discord.Embed(
            title="🎉 라이센스 등록 완료",
            description=f"{interaction.user.mention} 님의 라이센스가 성공적으로 등록되었습니다!",
            color=0x2ecc71
        )
        embed.add_field(name="🔑 입력한 코드", value=f"`{code}`", inline=False)
        embed.add_field(name="⏳ 만료 예정일", value=f"<t:{int(expire_time.timestamp())}:F> (<t:{int(expire_time.timestamp())}:R>)", inline=False)
        embed.add_field(name="🛡️ 지급된 역할", value=f"<@&{LICENSE_ROLE_ID}>", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            dm_embed = discord.Embed(
                title="💖 [라이센스 등록 및 역할 지급 완료]",
                description=f"**{interaction.guild.name}** 서버에서 라이센스 코드가 정상 등록되었습니다.",
                color=PASTEL_PINK
            )
            dm_embed.add_field(name="🔑 등록한 코드", value=f"`{code}`", inline=False)
            dm_embed.add_field(name="지급된 역할", value=f"<@&{LICENSE_ROLE_ID}>", inline=True)
            dm_embed.add_field(
                name="만료 예정일",
                value=f"<t:{int(expire_time.timestamp())}:F>\n(<t:{int(expire_time.timestamp())}:R>)",
                inline=False
            )
            dm_embed.set_footer(text="만료 시간이 지나면 역할이 자동으로 회수됩니다.")
            await interaction.user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        log_embed = discord.Embed(title="🔑 [라이센스 등록 기록]", color=0x2ecc71)
        log_embed.add_field(name="사용자", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
        log_embed.add_field(name="코드", value=f"`{code}`", inline=True)
        log_embed.add_field(name="만료일", value=f"{expire_time.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
        await send_log(interaction.guild, log_embed)


class RejectReasonModal(discord.ui.Modal, title="신청 거절 사유 입력"):
    def __init__(self, applicant: discord.Member, ticket_channel: discord.TextChannel):
        super().__init__()
        self.applicant = applicant
        self.ticket_channel = ticket_channel

    reason = discord.ui.TextInput(
        label="거절 사유를 입력하세요",
        placeholder="예: 인증 서류 불충분, 조건 미달 등",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = discord.Embed(
            title="❌ 진행자 신청이 거절되었습니다",
            description=f"{self.applicant.mention} 님의 진행자 신청이 아래 사유로 인해 거절되었습니다.",
            color=0xe74c3c
        )
        embed.add_field(name="📝 거절 사유", value=f"```\n{self.reason.value}\n```", inline=False)

        await self.ticket_channel.send(content=f"{self.applicant.mention}", embed=embed)
        await interaction.followup.send("거절 처리가 완료되었습니다.", ephemeral=True)


class HoldReasonModal(discord.ui.Modal, title="신청 보류 사유 입력"):
    def __init__(self, applicant: discord.Member, ticket_channel: discord.TextChannel):
        super().__init__()
        self.applicant = applicant
        self.ticket_channel = ticket_channel

    reason = discord.ui.TextInput(
        label="보류 사유를 입력하세요",
        placeholder="예: 추후 서류 재제출 필요, 추가 확인 중 등",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = discord.Embed(
            title="⏸️ 진행자 신청이 보류되었습니다",
            description=f"{self.applicant.mention} 님의 진행자 신청이 보류 처리되었습니다.",
            color=0xe67e22
        )
        embed.add_field(name="📝 보류 사유 및 안내", value=f"```\n{self.reason.value}\n```", inline=False)
        await self.ticket_channel.send(content=f"{self.applicant.mention}", embed=embed)
        await interaction.followup.send("보류 처리가 완료되었습니다.", ephemeral=True)


class AdminControlView(discord.ui.View):
    def __init__(self, applicant: discord.Member, ticket_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.ticket_channel = ticket_channel
        self.payment_msg = None

    @discord.ui.button(label="📝 개인정보 인증 완료", style=discord.ButtonStyle.primary, custom_id="admin_cert_ok")
    async def cert_ok(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="<a:loading:1500567324028043285> 입금 진행 중...",
            description=(
                f"{self.applicant.mention} 님, 개인정보 인증이 완료되었습니다.\n"
                f"아래 계좌로 입금 후 이중창 인증을 완료해 주세요.\n\n"
                f"• **우리은행 `49306531218364` (ㅈㅈㅎ)**\n"
                f"• **금액: 14,000원 (7일)**"
            ),
            color=0xf1c40f
        )
        self.payment_msg = await self.ticket_channel.send(embed=embed)
        await interaction.response.send_message("입금 진행 중 안내 메시지를 티켓 채널에 전송했습니다.", ephemeral=True)

    @discord.ui.button(label="🟢 입금 승인", style=discord.ButtonStyle.success, custom_id="admin_pay_approve")
    async def pay_approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        license_code = f"KEY-{uuid.uuid4().hex[:12].upper()}"
        license_db[license_code] = {
            "days": 7,
            "used": False,
            "user_id": None,
            "expires_at": None
        }

        completed_embed = discord.Embed(
            title="<a:check:1518257176811012217> 입금이 완료되었습니다",
            description=f"{self.applicant.mention} 님의 입금이 확인되어 **진행자 신청이 승인**되었습니다!",
            color=0x2ecc71
        )
        if self.payment_msg:
            try:
                await self.payment_msg.edit(embed=completed_embed)
            except discord.NotFound:
                await self.ticket_channel.send(embed=completed_embed)
        else:
            await self.ticket_channel.send(embed=completed_embed)

        lic_embed = discord.Embed(
            title="🔑 7일 라이센스 코드가 발급되었습니다",
            description=f"{self.applicant.mention} 님, 아래 발급된 코드를 복사하여 사용해 주세요.",
            color=0x3498db
        )
        lic_embed.add_field(name="발급된 라이센스 코드", value=f"```\n{license_code}\n```", inline=False)
        lic_embed.add_field(name="등록 안내", value="메인 채널의 **`🔑 라이센스 등록`** 버튼을 누른 후 위 코드를 입력하여 역할을 지급받으세요.", inline=False)
        
        await self.ticket_channel.send(embed=lic_embed)
        await self.ticket_channel.send(license_code)

        try:
            dm_embed = discord.Embed(
                title="🎁 [7일 라이센스 코드 발급 완료]",
                description=f"안녕하세요, **{interaction.guild.name}** 서버의 진행자 신청 승인에 따른 라이센스 코드가 발급되었습니다.",
                color=0x2ecc71
            )
            dm_embed.add_field(name="발급된 라이센스 코드", value=f"```\n{license_code}\n```", inline=False)
            dm_embed.add_field(name="유효기간", value="7일 (등록 시점부터 자동 차감)", inline=False)
            dm_embed.set_footer(text="메인 채널의 [라이센스 등록] 버튼을 눌러 등록을 완료해 주세요.")
            await self.applicant.send(embed=dm_embed)
        except discord.Forbidden:
            await self.ticket_channel.send(f"⚠️ {self.applicant.mention} 님의 DM이 차단되어 있어 DM 전송에 실패했습니다.")

        await interaction.response.send_message("입금 승인 및 7일 라이센스 발급을 완료했습니다.", ephemeral=True)

    @discord.ui.button(label="🔴 입금 거절", style=discord.ButtonStyle.danger, custom_id="admin_pay_reject")
    async def pay_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ 입금 거절 안내",
            description=f"{self.applicant.mention} 님, 입금 정보가 일치하지 않거나 입금이 확인되지 않았습니다.",
            color=0xe74c3c
        )
        await self.ticket_channel.send(embed=embed)
        await interaction.response.send_message("입금 거절 안내를 전송했습니다.", ephemeral=True)

    @discord.ui.button(label="⏸️ 신청 보류", style=discord.ButtonStyle.secondary, custom_id="admin_hold")
    async def hold(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(HoldReasonModal(applicant=self.applicant, ticket_channel=self.ticket_channel))

    @discord.ui.button(label="❌ 신청 거절", style=discord.ButtonStyle.danger, custom_id="admin_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(RejectReasonModal(applicant=self.applicant, ticket_channel=self.ticket_channel))

    @discord.ui.button(label="🔒 티켓 닫기", style=discord.ButtonStyle.secondary, custom_id="admin_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 5초 후 티켓 채널이 삭제됩니다...")
        await asyncio.sleep(5)
        await self.ticket_channel.delete()


class ApplicationModal(discord.ui.Modal, title="진행자 신청서 작성"):
    platform = discord.ui.TextInput(
        label="1. 진행자를 진행할 매체를 선택해 주세요.",
        placeholder="예: 디스코드, 오픈채팅, 둘 다 등",
        style=discord.TextStyle.short,
        required=True
    )
    reason = discord.ui.TextInput(
        label="2. 진행자를 하고 싶은 사유를 작성해 주세요.",
        placeholder="신청 사유 및 경험 등을 자유롭게 작성해 주세요.",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        category = guild.get_channel(CATEGORY_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category,
            overwrites=overwrites
        )

        await ticket_channel.send(
            f"{member.mention} 님 안녕하세요. <@&{ADMIN_ROLE_ID}> 가 곧 옵니다.\n"
            f"<a:loading:1500567324028043285> 개인정보 수집 동의 시 **동의**라고 입력해 주세요."
        )

        form_embed = discord.Embed(title="진행자 신청", color=0x3498db)
        form_embed.add_field(name="진행 매체", value=f"```\n{self.platform.value}\n```", inline=False)
        form_embed.add_field(name="신청 사유", value=f"```\n{self.reason.value}\n```", inline=False)
        await ticket_channel.send(embed=form_embed)

        admin_panel_channel = guild.get_channel(ADMIN_PANEL_CHANNEL_ID)
        if admin_panel_channel:
            admin_embed = discord.Embed(
                title="🛠️ 관리자 제어 패널",
                description=f"**신청자**: {member.mention} ({member.id})\n**티켓 채널**: {ticket_channel.mention}",
                color=0x34495e
            )
            await admin_panel_channel.send(
                embed=admin_embed,
                view=AdminControlView(applicant=member, ticket_channel=ticket_channel)
            )

        await interaction.followup.send(f"티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)


class ConfirmApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="예", style=discord.ButtonStyle.success, custom_id="btn_confirm_yes")
    async def confirm_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApplicationModal())

    @discord.ui.button(label="아니오", style=discord.ButtonStyle.danger, custom_id="btn_confirm_no")
    async def confirm_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("신청이 취소되었습니다.", ephemeral=True)


class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="진행자 신청", style=discord.ButtonStyle.success, emoji="🎫", custom_id="main_apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "**진행자를 신청하시겠습니까?**",
            view=ConfirmApplyView(),
            ephemeral=True
        )

    @discord.ui.button(label="라이센스 등록", style=discord.ButtonStyle.primary, emoji="🔑", custom_id="main_register_license")
    async def register_license(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LicenseRegisterModal())

    @discord.ui.button(label="진행자 설명", style=discord.ButtonStyle.secondary, emoji="📖", custom_id="main_info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📖 진행자 안내",
            description="""**디코 / 옾챗 내에서 구매자에게 판매하는 역할입니다.**
**구매 문의부터 거래 진행, 상품 지급까지 전부 담당해야 됩니다.**
일주일 <a:white_arrow:1489570377440165990> 14,000원
-# 최대 14일만 신청됩니다.""",
            color=PASTEL_PINK
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
# 3. 만료 자동 체크 태스크
# ==========================================
@tasks.loop(minutes=1)
async def check_expired_licenses():
    now = datetime.now()
    expired_users = []

    for user_id, info in list(user_licenses.items()):
        if now >= info["expires_at"]:
            expired_users.append((user_id, info))

    for user_id, info in expired_users:
        guild = bot.get_guild(info["guild_id"])
        if guild:
            member = guild.get_member(user_id)
            if member:
                role = guild.get_role(LICENSE_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role)

                try:
                    embed = discord.Embed(
                        title="⏰ 라이센스 만료 안내",
                        description="진행자 라이센스 기간(7일)이 만료되어 역할이 자동 회수되었습니다.",
                        color=0xe74c3c
                    )
                    await member.send(embed=embed)
                except discord.Forbidden:
                    pass

        del user_licenses[user_id]


# ==========================================
# 4. 컴포넌트 V2 (컨테이너 UI) 페이로드 생성
# ==========================================
def get_container_payload():
    return {
        "flags": 8192,  # IS_COMPONENTS_V2 (상자 내부에 버튼까지 감싸는 최신 UI 방식)
        "components": [
            {
                "type": 17,  # Container
                "accent_color": PASTEL_PINK,
                "components": [
                    {
                        "type": 10,  # TextDisplay
                        "content": (
                            "**<:store:1540740445330739210> 디코 / 오픈채팅 진행자 신청 및 등록**\n\n"
                            "• **진행자 신청**: 티켓 생성 후 안내 절차 진행\n"
                            "• **라이센스 등록**: 발급받은 코드 입력 시 역할 지급 및 만료 시간 적용 (7일)\n"
                            "-# <:emoji_109:1523981022826336406> 장난으로 생성한 경우 제재됩니다. <a:Warning_2:1490617932487594004>\n\n"
                            "아래 버튼을 눌러 진행하세요."
                        )
                    },
                    {
                        "type": 14,  # Separator (상자 내부 회색 구분선)
                        "divider": True,
                        "spacing": 1
                    },
                    {
                        "type": 1,  # ActionRow (버튼 그룹)
                        "components": [
                            {
                                "type": 2,
                                "style": 3,  # 초록색
                                "label": "진행자 신청",
                                "emoji": {"id": "1540740445330739210", "name": "store"},
                                "custom_id": "main_apply"
                            },
                            {
                                "type": 2,
                                "style": 1,  # 파란색
                                "label": "라이센스 등록",
                                "emoji": {"name": "🔑"},
                                "custom_id": "main_register_license"
                            },
                            {
                                "type": 2,
                                "style": 2,  # 회색
                                "label": "진행자 설명",
                                "emoji": {"name": "📖"},
                                "custom_id": "main_info"
                            }
                        ]
                    }
                ]
            }
        ]
    }


# ==========================================
# 5. 이벤트 및 메인 패널 생성 명령어
# ==========================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.strip() == "동의":
        embed = discord.Embed(
            title="🔒 개인정보 및 거래 인증 절차 안내",
            description="아래 절차에 따라 인증 정보를 제출해 주세요.",
            color=discord.Color.blue()
        )
        embed.add_field(name="1. 계좌 인증", value="ㆍ 은행명\nㆍ 계좌번호 (가상계좌 불가, 2개 이상)\nㆍ 예금주명", inline=False)
        embed.add_field(name="2. 전화번호 인증", value="ㆍ 설정 -> 전화번호가 보이는 화면 녹화본 제출", inline=False)
        embed.add_field(name="3. 거래 인증", value="ㆍ 네이버 카페, 옾챗, 디코 등 거래 내역 링크 또는 사진 제출", inline=False)

        if os.path.exists(IMAGE_FILE_NAME):
            image_file = discord.File(IMAGE_FILE_NAME, filename=IMAGE_FILE_NAME)
            embed.set_image(url=f"attachment://{IMAGE_FILE_NAME}")
            await message.channel.send(file=image_file, embed=embed)
        else:
            await message.channel.send(embed=embed)

    await bot.process_commands(message)


# 1️⃣ 채팅 명령어 방식 (!메인메뉴생성)
@bot.command(name="메인메뉴생성")
@commands.has_permissions(administrator=True)
async def make_main_chat(ctx):
    payload = get_container_payload()
    await bot.http.send_message(ctx.channel.id, **payload)
    try:
        await ctx.message.delete()
    except Exception:
        pass


# 2️⃣ 슬래시 명령어 방식 (/메인메뉴생성) -> 에러 안 나게 완전 보정 완료
@bot.tree.command(name="메인메뉴생성", description="[관리자] 메인 컨테이너 패널을 생성합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def make_main_slash(interaction: discord.Interaction):
    # 디스코드 응답을 처리해 무한 '생각 중...'을 방지
    await interaction.response.send_message("✅ 컨테이너 메인 패널을 생성했습니다!", ephemeral=True)
    payload = get_container_payload()
    await interaction.client.http.send_message(interaction.channel_id, **payload)


@bot.event
async def on_ready():
    print(f"로그인 성공: {bot.user.name}")
    bot.add_view(MainMenuView())
    check_expired_licenses.start()
    
    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료")
    except Exception as e:
        print(f"명령어 동기화 실패: {e}")


if TOKEN:
    bot.run(TOKEN)
else:
    print("오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
