import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os

# ==========================================
# 1. 설정 및 ID 상수
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")

CATEGORY_ID = 1457078078294458390       # 티켓이 생성될 카테고리 ID
ADMIN_ROLE_ID = 1458178323434836199     # 관리자 역할 ID
LOG_CHANNEL_ID = 1540722623883911250    # 로그 전송 채널 ID
ADMIN_PANEL_CHANNEL_ID = 1540725362776871034  # 관리자 제어 패널 전송 채널 ID
IMAGE_FILE_NAME = "guide.png"           # '동의' 입력 시 함께 전송할 이미지 파일명

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 로그 전송 헬퍼 함수
async def send_log(guild: discord.Guild, embed: discord.Embed):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)


# ==========================================
# 2. UI 컴포넌트
# ==========================================

# [신청 거절 사유 입력 모달]
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
        embed.add_field(
            name="📝 거절 사유",
            value=f"```\n{self.reason.value}\n```",
            inline=False
        )

        await self.ticket_channel.send(content=f"{self.applicant.mention}", embed=embed)
        await interaction.followup.send("거절 처리가 완료되었습니다. 5초 후 티켓이 삭제됩니다.", ephemeral=True)

        log_embed = discord.Embed(
            title="🔴 [신청 거절 기록]",
            color=0xe74c3c
        )
        log_embed.add_field(name="신청자", value=f"{self.applicant.mention} ({self.applicant.id})", inline=True)
        log_embed.add_field(name="처리 관리자", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="거절 사유", value=f"```\n{self.reason.value}\n```", inline=False)
        log_embed.set_footer(text=f"티켓 채널: {self.ticket_channel.name}")
        await send_log(interaction.guild, log_embed)

        await asyncio.sleep(5)
        await self.ticket_channel.delete()


# [신청 보류 사유 입력 모달]
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
        embed.add_field(
            name="📝 보류 사유 및 안내",
            value=f"```\n{self.reason.value}\n```",
            inline=False
        )
        await self.ticket_channel.send(content=f"{self.applicant.mention}", embed=embed)
        await interaction.followup.send("보류 처리가 완료되었습니다.", ephemeral=True)

        log_embed = discord.Embed(
            title="🟠 [신청 보류 기록]",
            color=0xe67e22
        )
        log_embed.add_field(name="신청자", value=f"{self.applicant.mention} ({self.applicant.id})", inline=True)
        log_embed.add_field(name="처리 관리자", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="보류 사유", value=f"```\n{self.reason.value}\n```", inline=False)
        log_embed.set_footer(text=f"티켓 채널: {self.ticket_channel.name}")
        await send_log(interaction.guild, log_embed)


# [관리자 전용 제어 패널]
class AdminControlView(discord.ui.View):
    def __init__(self, applicant: discord.Member, ticket_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.ticket_channel = ticket_channel
        self.payment_msg = None  # 입금 진행 중 메시지 객체 저장용

    # 1. 개인정보 인증 완료 버튼 (입금 진행 중 메시지 생성)
    @discord.ui.button(label="📝 개인정보 인증 완료", style=discord.ButtonStyle.primary, custom_id="admin_cert_ok")
    async def cert_ok(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="<a:loading:1500567324028043285> 💳 입금 진행 중...",
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

    # 2. 입금 승인 버튼 (입금 진행 중 임베드를 입금 완료 임베드로 수정)
    @discord.ui.button(label="🟢 입금 승인", style=discord.ButtonStyle.success, custom_id="admin_pay_approve")
    async def pay_approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        completed_embed = discord.Embed(
            title="<a:check:1518257176811012217> 🎉 입금이 완료되었습니다",
            description=f"{self.applicant.mention} 님의 입금이 확인되어 **진행자 신청이 승인**되었습니다!",
            color=0x2ecc71
        )

        # 기존 입금 진행 중 메시지가 있으면 수정하고, 없으면 새 메시지 전송
        if self.payment_msg:
            try:
                await self.payment_msg.edit(embed=completed_embed)
            except discord.NotFound:
                await self.ticket_channel.send(embed=completed_embed)
        else:
            await self.ticket_channel.send(embed=completed_embed)

        await interaction.response.send_message("입금 승인 및 임베드 수정을 완료했습니다.", ephemeral=True)

        log_embed = discord.Embed(
            title="🟢 [신청 승인 기록]",
            color=0x2ecc71
        )
        log_embed.add_field(name="신청자", value=f"{self.applicant.mention} ({self.applicant.id})", inline=True)
        log_embed.add_field(name="처리 관리자", value=f"{interaction.user.mention}", inline=True)
        log_embed.set_footer(text=f"티켓 채널: {self.ticket_channel.name}")
        await send_log(interaction.guild, log_embed)

    # 3. 입금 거절 버튼
    @discord.ui.button(label="🔴 입금 거절", style=discord.ButtonStyle.danger, custom_id="admin_pay_reject")
    async def pay_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ 입금 거절 안내",
            description=f"{self.applicant.mention} 님, 입금 정보가 일치하지 않거나 입금이 확인되지 않았습니다. 계좌 및 입금자명을 재확인 후 문의해 주세요.",
            color=0xe74c3c
        )
        await self.ticket_channel.send(embed=embed)
        await interaction.response.send_message("입금 거절 안내를 전송했습니다.", ephemeral=True)

        log_embed = discord.Embed(
            title="🔴 [입금 거절 기록]",
            color=0xe74c3c
        )
        log_embed.add_field(name="신청자", value=f"{self.applicant.mention} ({self.applicant.id})", inline=True)
        log_embed.add_field(name="처리 관리자", value=f"{interaction.user.mention}", inline=True)
        log_embed.set_footer(text=f"티켓 채널: {self.ticket_channel.name}")
        await send_log(interaction.guild, log_embed)

    # 4. 신청 보류 버튼
    @discord.ui.button(label="⏸️ 신청 보류", style=discord.ButtonStyle.secondary, custom_id="admin_hold")
    async def hold(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_modal(HoldReasonModal(applicant=self.applicant, ticket_channel=self.ticket_channel))

    # 5. 신청 거절 버튼
    @discord.ui.button(label="❌ 신청 거절", style=discord.ButtonStyle.danger, custom_id="admin_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_modal(RejectReasonModal(applicant=self.applicant, ticket_channel=self.ticket_channel))

    # 6. 티켓 닫기 버튼
    @discord.ui.button(label="🔒 티켓 닫기", style=discord.ButtonStyle.secondary, custom_id="admin_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 5초 후 티켓 채널이 삭제됩니다...")

        log_embed = discord.Embed(
            title="🔒 [티켓 종결 기록]",
            color=0x95a5a6
        )
        log_embed.add_field(name="신청자", value=f"{self.applicant.mention} ({self.applicant.id})", inline=True)
        log_embed.add_field(name="종결 처리자", value=f"{interaction.user.mention}", inline=True)
        log_embed.set_footer(text=f"티켓 채널명: {self.ticket_channel.name}")
        await send_log(interaction.guild, log_embed)

        await asyncio.sleep(5)
        await self.ticket_channel.delete()


# [신청 양식 모달 창]
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

        # 1. 티켓 채널 생성
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category,
            overwrites=overwrites
        )

        # 2. 상단 멘션 및 동의 안내 문구 출력
        await ticket_channel.send(
            f"{member.mention} 님 안녕하세요. <@&{ADMIN_ROLE_ID}> 가 곧 옵니다.\n"
            f"<a:loading:1500567324028043285> 개인정보 수집 동의 시 **동의**라고 입력해 주세요."
        )

        # 3. 신청서 내용 임베드 전송
        form_embed = discord.Embed(
            title="진행자 신청",
            color=0x3498db
        )
        form_embed.add_field(
            name="진행 매체",
            value=f"```\n{self.platform.value}\n```",
            inline=False
        )
        form_embed.add_field(
            name="신청 사유",
            value=f"```\n{self.reason.value}\n```",
            inline=False
        )
        await ticket_channel.send(embed=form_embed)

        # 4. 지정된 관리자 채널(ID: 1540725362776871034)에 관리자 제어 패널 전송
        admin_panel_channel = guild.get_channel(ADMIN_PANEL_CHANNEL_ID)
        if admin_panel_channel:
            admin_embed = discord.Embed(
                title="🛠️ 관리자 제어 패널",
                description=(
                    f"**신청자**: {member.mention} ({member.id})\n"
                    f"**티켓 채널**: {ticket_channel.mention}\n\n"
                    f"• **개인정보 인증 완료**: 입금 진행 중 안내 전송\n"
                    f"• **입금 승인**: 입금 진행 임베드를 완료 상태로 변경 및 로그 기록\n"
                    f"• **입금 거절**: 입금 거절 안내 전송 및 로그 기록\n"
                    f"• **신청 보류**: 보류 사유 전송 및 로그 기록\n"
                    f"• **신청 거절**: 거절 사유 전송 후 티켓 삭제 및 로그 기록\n"
                    f"• **티켓 닫기**: 해당 티켓 삭제 및 로그 기록"
                ),
                color=0x34495e
            )
            await admin_panel_channel.send(
                embed=admin_embed,
                view=AdminControlView(applicant=member, ticket_channel=ticket_channel)
            )

        # 5. 신청 접수 로그 기록
        log_embed = discord.Embed(
            title="📥 [신청서 접수 기록]",
            color=0x3498db
        )
        log_embed.add_field(name="신청자", value=f"{member.mention} ({member.id})", inline=True)
        log_embed.add_field(name="티켓 채널", value=f"{ticket_channel.mention}", inline=True)
        log_embed.add_field(name="진행 매체", value=f"```\n{self.platform.value}\n```", inline=False)
        log_embed.add_field(name="신청 사유", value=f"```\n{self.reason.value}\n```", inline=False)
        await send_log(guild, log_embed)

        await interaction.followup.send(f"티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)


# [신청 여부 확인 버튼 (예 / 아니오)]
class ConfirmApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="예", style=discord.ButtonStyle.success, custom_id="btn_confirm_yes")
    async def confirm_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApplicationModal())

    @discord.ui.button(label="아니오", style=discord.ButtonStyle.danger, custom_id="btn_confirm_no")
    async def confirm_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("신청이 취소되었습니다.", ephemeral=True)


# [메인 메뉴 고정 버튼]
class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 진행자 신청", style=discord.ButtonStyle.primary, custom_id="main_apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "**진행자를 신청하시겠습니까?**",
            view=ConfirmApplyView(),
            ephemeral=True
        )

    @discord.ui.button(label="📖 진행자 설명", style=discord.ButtonStyle.secondary, custom_id="main_info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📖 진행자 안내",
            description="""**디코 / 옾챗 내에서 구매자에게 판매하는 역할입니다. **
**구매 문의부터 거래 진행, 상품 지급까지 전부 당담해야 됩니다**
일주일 <a:white_arrow:1489570377440165990> 14,000원
-# 최대 14일만 신청됩니다.""",
            color=0x3498db
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
# 3. 이벤트
# ==========================================

# '동의' 입력 감지
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

        embed.add_field(
            name="1. 계좌 인증",
            value=(
                "ㆍ 은행명 (서로 다른 은행명)\n"
                "ㆍ 계좌번호 (가상계좌 불가, 2개이상)\n"
                "ㆍ 예금주명\n\n"
                "※ 필요 시 본인 명의 확인을 위해 예금주가 표시된 화면을 요청할 수 있습니다."
            ),
            inline=False
        )

        embed.add_field(
            name="2. 전화번호 인증",
            value=(
                "인증 방법 (전화번호)\n\n"
                "**iOS :**\n"
                "1 . 설정 앱을 실행합니다.\n"
                "2 . 검색란에 ‘ 전화 ’ 입력 후 전화 아이콘 클릭.\n"
                "3 . 나의 전화번호가 보이는 화면을 준비합니다.\n"
                "4 . 저와 대화 중인 채팅창이 함께 보이도록 화면을 녹화하여 제출해 주세요.\n\n"
                "**Android :**\n"
                "1 . 설정 앱을 실행합니다.\n"
                "2 . 휴대전화 정보 또는 휴대전화 정보 → 상태 정보로 이동합니다.\n"
                "     (기기에 따라 SIM 상태, 내 전화번호 메뉴일 수도 있습니다.)\n"
                "3 . 전화번호가 보이는 화면을 준비합니다.\n"
                "4 . 저와 대화 중인 채팅창이 함께 보이도록 화면을 녹화하여 제출해 주세요."
            ),
            inline=False
        )

        embed.add_field(
            name="3. 거래 인증",
            value=(
                "아래 정보를 사진 또는 링크로 보내주세요.\n\n"
                "ㆍ 네이버 카페, 옾챗, 디코 등 거래 내역이 확인 가능한 링크 또는 사진을 보내주세요\n"
                "ㆍ 첫 거래 날짜가 확인 가능하면 함께 보내주세요\n\n"
                "⚠️ **주의사항**\n"
                "모두 현시각과 다를 시, 인정이 되지 않습니다. 도용, 합성 및 AI 의심이 날 경우, 위 방법과 다른 인증 수단을 요청할 수 있으니, 이 점 참고해 주시길 바랍니다."
            ),
            inline=False
        )

        if os.path.exists(IMAGE_FILE_NAME):
            image_file = discord.File(IMAGE_FILE_NAME, filename=IMAGE_FILE_NAME)
            embed.set_image(url=f"attachment://{IMAGE_FILE_NAME}")
            await message.channel.send(file=image_file, embed=embed)
        else:
            await message.channel.send(embed=embed)

    await bot.process_commands(message)


# 메인 메뉴 생성 슬래시 명령어
@bot.tree.command(name="메인메뉴생성", description="[관리자] 신청 메인 버튼 메시지를 생성합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def make_main(interaction: discord.Interaction):
    embed = discord.Embed(
        title="<:link_thr:1499081032832385284> 디코 / 오픈채팅 진행자 신청",
        description="""판매자 신청을 원하시면 아래 버튼을 눌러주세요.

• 판매자 신청 티켓 생성 후 간단한 확인 절차 진행
• 판매자로 선정될 경우 오픈채팅 내에서 상품 판매 가능
• 판매 활동 중에는 서버 내 거래 규정을 반드시 준수
-# <:emoji_109:1523981022826336406> 장난으로 생성한 경우 제재됩니다. <a:Warning_2:1490617932487594004>""",
        color=0x2ecc71
    )
    await interaction.channel.send(embed=embed, view=MainMenuView())
    await interaction.response.send_message("메인 메뉴 생성 완료!", ephemeral=True)


@bot.event
async def on_ready():
    print(f"로그인 성공: {bot.user.name}")
    bot.add_view(MainMenuView())
    await bot.tree.sync()


if TOKEN:
    bot.run(TOKEN)
else:
    print("오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
