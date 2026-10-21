// 서버 복제 봇 (discord.js v14)
// 설치: npm i discord.js
// 실행: TOKEN=봇토큰 node index.js
const {
  Client,
  GatewayIntentBits,
  ChannelType,
  OverwriteType,
  PermissionFlagsBits,
  SlashCommandBuilder,
  MessageFlags,
} = require("discord.js");

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

const command = new SlashCommandBuilder()
  .setName("clone")
  .setDescription("다른 서버의 역할/채널 구조를 이 서버로 복제합니다")
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .setDMPermission(false)
  .addStringOption((o) =>
    o.setName("server_id").setDescription("복제할 원본 서버 ID").setRequired(true)
  )
  .addBooleanOption((o) =>
    o.setName("wipe").setDescription("복제 전에 이 서버의 기존 채널/역할 삭제").setRequired(false)
  )
  .addBooleanOption((o) =>
    o.setName("emojis").setDescription("이모지도 복제").setRequired(false)
  );

client.once("clientReady", async () => {
  await client.application.commands.set([command]);
  console.log(`로그인: ${client.user.tag}`);
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

client.on("interactionCreate", async (i) => {
  if (!i.isChatInputCommand() || i.commandName !== "clone") return;

  const target = i.guild;
  const sourceId = i.options.getString("server_id").trim();
  const wipe = i.options.getBoolean("wipe") ?? false;
  const withEmojis = i.options.getBoolean("emojis") ?? false;

  await i.deferReply({ flags: MessageFlags.Ephemeral });
  const say = (t) => i.editReply(t).catch(() => {});

  // 원본 서버 확인 (봇이 들어가 있어야 함)
  let source;
  try {
    source = await client.guilds.fetch(sourceId);
  } catch {
    return say("❌ 원본 서버를 찾을 수 없어요. 봇이 그 서버에도 초대돼 있어야 해요.");
  }
  if (source.id === target.id) return say("❌ 같은 서버는 복제할 수 없어요.");

  // 실행한 사람이 원본 서버에서도 관리자인지 확인
  try {
    const m = await source.members.fetch(i.user.id);
    if (!m.permissions.has(PermissionFlagsBits.Administrator)) {
      return say("❌ 원본 서버에서도 관리자 권한이 있어야 복제할 수 있어요.");
    }
  } catch {
    return say("❌ 원본 서버에서 당신을 찾을 수 없어요. 해당 서버 멤버여야 해요.");
  }

  try {
    await Promise.all([source.roles.fetch(), source.channels.fetch()]);

    // 1) 기존 항목 삭제
    if (wipe) {
      await say("🧹 기존 채널/역할 삭제 중...");
      for (const ch of target.channels.cache.values()) await ch.delete().catch(() => {});
      for (const r of target.roles.cache.values()) {
        if (r.id !== target.id && !r.managed && r.editable) await r.delete().catch(() => {});
      }
    }

    // 2) 역할 복제 (@everyone 제외, 봇/연동 역할 제외)
    await say("🎭 역할 복제 중...");
    const roleMap = new Map([[source.id, target.id]]); // @everyone 매핑
    await target.roles.everyone.setPermissions(source.roles.everyone.permissions).catch(() => {});

    // 새 역할은 맨 아래에 생성되므로, 높은 역할부터 만들어야 순서가 유지됨
    const roles = [...source.roles.cache.values()]
      .filter((r) => r.id !== source.id && !r.managed)
      .sort((a, b) => b.position - a.position);

    for (const r of roles) {
      const created = await target.roles
        .create({
          name: r.name,
          color: r.color,
          hoist: r.hoist,
          mentionable: r.mentionable,
          permissions: r.permissions,
        })
        .catch(() => null);
      if (created) roleMap.set(r.id, created.id);
    }

    // 권한 덮어쓰기 변환 (역할만 복제, 멤버별 설정은 제외)
    const mapOverwrites = (channel) =>
      channel.permissionOverwrites.cache
        .filter((o) => o.type === OverwriteType.Role && roleMap.has(o.id))
        .map((o) => ({
          id: roleMap.get(o.id),
          type: OverwriteType.Role,
          allow: o.allow,
          deny: o.deny,
        }));

    // 3) 카테고리 복제
    await say("📁 카테고리 복제 중...");
    const sorted = (list) => [...list].sort((a, b) => a.rawPosition - b.rawPosition);
    const all = [...source.channels.cache.values()].filter((c) => !c.isThread());

    const categoryMap = new Map();
    for (const c of sorted(all.filter((c) => c.type === ChannelType.GuildCategory))) {
      const created = await target.channels
        .create({
          name: c.name,
          type: ChannelType.GuildCategory,
          permissionOverwrites: mapOverwrites(c),
        })
        .catch(() => null);
      if (created) categoryMap.set(c.id, created.id);
    }

    // 4) 채널 복제
    await say("💬 채널 복제 중...");
    const failed = [];
    for (const c of sorted(all.filter((c) => c.type !== ChannelType.GuildCategory))) {
      const base = {
        name: c.name,
        type: c.type,
        parent: c.parentId ? categoryMap.get(c.parentId) : undefined,
        permissionOverwrites: mapOverwrites(c),
      };

      switch (c.type) {
        case ChannelType.GuildText:
        case ChannelType.GuildAnnouncement:
        case ChannelType.GuildForum:
          Object.assign(base, {
            topic: c.topic ?? undefined,
            nsfw: c.nsfw,
            rateLimitPerUser: c.rateLimitPerUser ?? 0,
          });
          break;
        case ChannelType.GuildVoice:
        case ChannelType.GuildStageVoice:
          Object.assign(base, {
            bitrate: Math.min(c.bitrate, target.maximumBitrate),
            userLimit: c.userLimit,
          });
          break;
        default:
          continue; // 지원하지 않는 타입은 건너뜀
      }

      let created = await target.channels.create(base).catch(() => null);

      // 커뮤니티 기능이 꺼진 서버에선 공지/포럼/스테이지 생성 실패 → 텍스트/음성으로 대체
      if (!created && c.type === ChannelType.GuildAnnouncement) {
        created = await target.channels.create({ ...base, type: ChannelType.GuildText }).catch(() => null);
      } else if (!created && c.type === ChannelType.GuildStageVoice) {
        created = await target.channels.create({ ...base, type: ChannelType.GuildVoice }).catch(() => null);
      }
      if (!created) failed.push(c.name);
    }

    // 5) 이모지 (선택)
    let emojiCount = 0;
    if (withEmojis) {
      await say("😀 이모지 복제 중...");
      await source.emojis.fetch();
      for (const e of source.emojis.cache.values()) {
        const ok = await target.emojis
          .create({ attachment: e.imageURL({ extension: e.animated ? "gif" : "png" }), name: e.name })
          .catch(() => null);
        if (ok) emojiCount++;
        else break; // 슬롯이 가득 찼을 가능성이 높음
        await sleep(300);
      }
    }

    await say(
      `✅ 복제 완료!\n역할 ${roleMap.size - 1}개, 채널 ${all.length - categoryMap.size}개, 카테고리 ${categoryMap.size}개` +
        (withEmojis ? `, 이모지 ${emojiCount}개` : "") +
        (failed.length ? `\n⚠️ 실패한 채널: ${failed.join(", ")}` : "")
    );
  } catch (err) {
    console.error(err);
    say(`❌ 오류: ${err.message}`);
  }
});

client.login(process.env.TOKEN);
