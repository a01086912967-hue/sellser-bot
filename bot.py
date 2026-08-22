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
IMAGE_FILE_NAME = "guide.png"           # '동의' 입력 시 함께 전송할 이미지 파일명

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# 2. UI 컴포넌트
# ==========================================

# [신청 양식 모달 창 (나만 보이는 입력 팝업)]
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

        # 카테고리 내에 티켓 채널 생성
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category,
            overwrites=overwrites
        )

        # 제출된 신청 양식 임베드
        form_embed = discord.Embed(
            title="📋 진행자 신청 양식 제출 내용",
            color=0x3498db
        )
        form_embed.add_field(name="👤 신청자", value=member.mention, inline=False)
        form_embed.add_field(name="📍 진행 매체", value=self.platform.value, inline=False)
        form_embed.add_field(name="📝 신청 사유", value=self.reason.value, inline=False)

        # 관리자 제어 패널 임베드
        admin_embed = discord.Embed(
            title="🛠️ 관리자 제어 패널",
            description=(
                f"**신청자**: {member.mention}\n\n"
                f"신청자가 '동의' 입력 후 개인정보를 제출하면 아래 버튼으로 진행해 주세요.\n"
                f"• **개인정보 인증 완료**: 입금 계좌 안내 전송\n"
                f"• **입금 확인 완료**: 입금 완료 안내 전송\n"
                f"• **티켓 닫기**: 해당 신청 채널 티켓 삭제"
            ),
            color=0x34495e
        )

        # 티켓 채널로 메시지 전송
        await ticket_channel.send(embed=form_embed)
        await ticket_channel.send(embed=admin_embed, view=AdminControlView(applicant=member))

        # 사용자에게 안내 메시지 전달
        await interaction.followup.send(f"티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)


# [신청 여부 확인 버튼 (예 / 아니오)]
class ConfirmApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="예", style=discord.ButtonStyle.success, custom_id="btn_confirm_yes")
    async def confirm_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 예 선택 시 신청 양식 모달을 띄움
        await interaction.response.send_modal(ApplicationModal())

    @discord.ui.button(label="아니오", style=discord.ButtonStyle.danger, custom_id="btn_confirm_no")
    async def confirm_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("신청이 취소되었습니다.", ephemeral=True)


# [티켓 내 관리자 전용 제어 패널]
class AdminControlView(discord.ui.View):
    def __init__(self, applicant: discord.Member):
        super().__init__(timeout=None)
        self.applicant = applicant

    # 1. 개인정보 인증 완료 버튼
    @discord.ui.button(label="📝 개인정보 인증 완료", style=discord.ButtonStyle.primary, custom_id="admin_cert_ok")
    async def cert_ok(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="💳 입금 안내",
            description=(
                f"{self.applicant.mention} 님, 개인정보 인증이 완료되었습니다.\n\n"
                f"• **우리은행 `49306531218364` (ㅈㅈㅎ)**\n"
                f"• **금액: 14,000원 (7일)**\n\n"
                f"입금하고 이중창 인증 후 관리자가 확인하여 처리됩니다."
            ),
            color=0xf1c40f
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("인증 완료 및 입금 안내 메시지를 전송했습니다.", ephemeral=True)

    # 2. 입금 확인 버튼
    @discord.ui.button(label="💳 입금 확인 완료", style=discord.ButtonStyle.success, custom_id="admin_pay_ok")
    async def pay_ok(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎉 입금 확인 완료",
            description=f"{self.applicant.mention} 님의 입금이 확인되었습니다.",
            color=0x2ecc71
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("입금 확인 처리되었습니다.", ephemeral=True)

    # 3. 티켓 닫기 버튼
    @discord.ui.button(label="🔒 티켓 닫기", style=discord.ButtonStyle.danger, custom_id="admin_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 클릭할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 5초 후 티켓 채널이 삭제됩니다...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


# [메인 메뉴 고정 버튼]
class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 진행자 신청", style=discord.ButtonStyle.primary, custom_id="main_apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 신청 버튼 누를 시 본인에게만 보이는 질문 메시지 전송
        await interaction.response.send_message(
            "❓ **진행자를 신청하시겠습니까?**",
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
