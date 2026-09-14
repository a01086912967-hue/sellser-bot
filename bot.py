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

CATEGORY_ID = 1457078078294458390        # 티켓 카테고리 ID
ADMIN_ROLE_ID = 1458178323434836199      # 관리자 역할 ID
LOG_CHANNEL_ID = 1540722623883911250     # 로그 채널 ID
ADMIN_PANEL_CHANNEL_ID = 1540725362776871034  # 관리자 제어 패널 채널 ID
LICENSE_ROLE_ID = 1540733768275333270    # 라이센스 보유자 역할 ID (<@&1540733768275333270>)
IMAGE_FILE_NAME = "guide.png"            # 안내 이미지

# 색상 상수
PASTEL_PINK = 0xFFB6C1                  # 파스텔 연핑크 색상 코드

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 메모리 데이터 저장용
license_db = {}
user_licenses = {}

# 로그 전송 헬퍼 함수
async def send_log(guild: discord.Guild, embed: discord.Embed):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)


# ==========================================
# 2. UI 컴포넌트 & 모달
# ==========================================

# [라이센스 코드 등록 모달]
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

        # 라이센스 등록 처리 (7일 차감 시작)
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

        # 역할 부여
        role = interaction.guild.get_role(LICENSE_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)

        # 상호작용 채널에 완료 임베드 출력
        embed = discord.Embed(
            title="🎉 라이센스 등록 완료",
            description=f"{interaction.user.mention} 님의 라이센스가 성공적으로 등록되었습니다!",
            color=0x2ecc71
        )
        embed.add_field(name="🔑 입력한 코드", value=f"`{code}`", inline=False)
        embed.add_field(name="⏳ 만료 예정일", value=f"<t:{int(expire_time.timestamp())}:F> (<t:{int(expire_time.timestamp())}:R>)", inline=False)
        embed.add_field(name="🛡️ 지급된 역할", value=f"<@&{LICENSE_ROLE_ID}>", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

        # 📩 사용자 개인 DM 알림 전송
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
            pass  # DM이 막혀 있는 경우 예외 처리

        # 등록 로그 작성
        log_embed = discord.Embed(title="🔑 [라이센스 등록 기록]", color=0x2ecc71)
        log_embed.add_field(name="사용자", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
        log_embed.add_field(name="코드", value=f"`{code}`", inline=True)
        log_embed.add_field(name="만료일", value=f"{expire_time.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
        await send_log(interaction.guild, log_embed)


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
        embed.add_field(name="📝 거절 사유", value=f"```\n{self.reason.value}\n```", inline=False)

        await self.ticket_channel.send(content=f"{self.applicant.mention}", embed=embed)
        await interaction.followup.send("거절 처리가 완료되었습니다.", ephemeral=True)

        log_embed = discord.Embed(title="🔴 [신청 거절 기록]", color=0xe74c3c)
        log_embed.add_field(name="신청자", value=f"{self.applicant.mention} ({self.applicant.id})", inline=True)
        log_embed.add_field(name="처리 관리자", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="거절 사유", value=f"```\n{self.reason.value}\n```", inline=False)
        log_embed.set_footer(text=f"티켓 채널: {self.ticket_channel.name}")
        await send_log(interaction.guild, log_embed)


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
        embed.add_field(name="📝 보류 사유 및 안내", value=f"```\n{self.reason.value}\n
