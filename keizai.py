import discord
import os
from discord import app_commands
from discord.ext import commands
import random

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 簡易データベース（サーバーごとに分けた構造）
# 構造: { guild_id: { user_id: { "money": 所持金, "bank": 銀行預金, "debt": 借金 } } }
economy_db = {}

def get_user(guild_id, user_id):
    if guild_id not in economy_db:
        economy_db[guild_id] = {}
    if user_id not in economy_db[guild_id]:
        economy_db[guild_id][user_id] = {"money": 1000, "bank": 0, "debt": 0}
    return economy_db[guild_id][user_id]

# 一般管理者かどうかを判定する関数
def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# ボット主（オーナー）かどうかを判定する関数
async def is_owner(interaction: discord.Interaction):
    app_info = await bot.application_info()
    return interaction.user.id == app_info.owner.id


# --- 1. 請求書ボタンView ---
class InvoiceView(discord.ui.View):
    def __init__(self, guild_id: int, target_user: discord.User, sender: discord.User, amount: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.target_user = target_user
        self.sender = sender
        self.amount = amount

    @discord.ui.button(label="支払う", style=discord.ButtonStyle.green)
    async def pay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("あなた宛ての請求書ではありません！", ephemeral=True)
            return

        target_data = get_user(self.guild_id, self.target_user.id)
        sender_data = get_user(self.guild_id, self.sender.id)

        if target_data["money"] < self.amount:
            await interaction.response.send_message("所持金が足りないため支払えませんでした！", ephemeral=True)
            return

        target_data["money"] -= self.amount
        sender_data["money"] += self.amount

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=f"✅ 請求書を承認し、**{self.amount:,}円** を支払いました！",
            view=self
        )

    @discord.ui.button(label="断る", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("あなた宛ての請求書ではありません！", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=f"❌ 請求書を拒否しました。",
            view=self
        )


# --- 2. 起動時の同期処理 ---
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"同期完了: {len(synced)}個のスラッシュコマンドを読み込みました。")
    except Exception as e:
        print(e)
    print(f"ログインしました: {bot.user.name}")


# --- 3. 経済スラッシュコマンド（すべて本人のみ表示） ---

@bot.tree.command(name="wallet", description="このサーバーでの所持金や銀行残高を確認します")
async def wallet(interaction: discord.Interaction):
    data = get_user(interaction.guild_id, interaction.user.id)
    embed = discord.Embed(title=f"💰 {interaction.user.name}さんの財産（このサーバー）", color=discord.Color.gold())
    embed.add_field(name="手持ち現金", value=f"{data['money']:,} 円", inline=False)
    embed.add_field(name="銀行預金", value=f"{data['bank']:,} 円", inline=False)
    embed.add_field(name="借金", value=f"{data['debt']:,} 円", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="work", description="お仕事をして現金を稼ぎます（1時間に1回）")
@app_commands.checks.cooldown(1, 3600)
async def work(interaction: discord.Interaction):
    data = get_user(interaction.guild_id, interaction.user.id)
    earned = random.randint(300, 1500)
    data["money"] += earned
    await interaction.response.send_message(f"👷 お仕事をして **{earned:,}円** 稼ぎました！", ephemeral=True)

@work.error
async def work_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        retry_after = int(error.retry_after)
        hours = retry_after // 3600
        minutes = (retry_after % 3600) // 60
        seconds = retry_after % 60
        
        time_text = ""
        if hours > 0: time_text += f"{hours}時間"
        if minutes > 0: time_text += f"{minutes}分"
        time_text += f"{seconds}秒"
        
        await interaction.response.send_message(
            f"⏳ 働きすぎです！次の仕事まであと **{time_text}** お待ちください。",
            ephemeral=True
        )

@bot.tree.command(name="deposit", description="銀行にお金を預けます")
@app_commands.describe(amount="預ける金額")
async def deposit(interaction: discord.Interaction, amount: int):
    data = get_user(interaction.guild_id, interaction.user.id)
    if data["money"] < amount or amount <= 0:
        await interaction.response.send_message("預け入れるお金が足りないか、不正な金額です。", ephemeral=True)
        return
    data["money"] -= amount
    data["bank"] += amount
    await interaction.response.send_message(f"🏦 銀行に **{amount:,}円** 預け入れました。", ephemeral=True)

@bot.tree.command(name="withdraw", description="銀行からお金を引き出します")
@app_commands.describe(amount="引き出す金額")
async def withdraw(interaction: discord.Interaction, amount: int):
    data = get_user(interaction.guild_id, interaction.user.id)
    if data["bank"] < amount or amount <= 0:
        await interaction.response.send_message("銀行の残高が足りないか、不正な金額です。", ephemeral=True)
        return
    data["bank"] -= amount
    data["money"] += amount
    await interaction.response.send_message(f"🏧 銀行から **{amount:,}円** 引き出しました。", ephemeral=True)

@bot.tree.command(name="gamble", description="ギャンブルで一攫千金（倍になるか消えるか）")
@app_commands.describe(amount="賭ける金額")
async def gamble(interaction: discord.Interaction, amount: int):
    data = get_user(interaction.guild_id, interaction.user.id)
    if data["money"] < amount or amount <= 0:
        await interaction.response.send_message("手持ちの現金が足りません！", ephemeral=True)
        return
    
    if random.random() < 0.45:
        data["money"] += amount
        await interaction.response.send_message(f"🎰 ギャンブルに**勝利**！所持金が倍の **+{amount:,}円** 増えました！", ephemeral=True)
    else:
        data["money"] -= amount
        await interaction.response.send_message(f"💸 ギャンブルに**負け**ました… **-{amount:,}円** 失いました。", ephemeral=True)

@bot.tree.command(name="stock", description="株投資で一発逆転を狙います")
@app_commands.describe(amount="投資する金額")
async def stock(interaction: discord.Interaction, amount: int):
    data = get_user(interaction.guild_id, interaction.user.id)
    if data["money"] < amount or amount <= 0:
        await interaction.response.send_message("手持ちの現金が足りません！", ephemeral=True)
        return
    
    rate = random.choice([-0.8, -0.5, 0.2, 0.5, 1.2, 2.0])
    result = int(amount * rate)
    data["money"] += result

    if result > 0:
        await interaction.response.send_message(f"📈 株価が上昇！ **+{result:,}円** の利益が出ました！", ephemeral=True)
    else:
        await interaction.response.send_message(f"📉 株価が大暴落… **{result:,}円** の損失を出しました。", ephemeral=True)


# --- 4. 請求書コマンド ---

@bot.tree.command(name="invoice", description="指定したユーザーに請求書を送ります")
@app_commands.describe(member="請求する相手", amount="請求する金額")
async def invoice(interaction: discord.Interaction, member: discord.Member, amount: int):
    if member.bot:
        await interaction.response.send_message("ボットに請求書は送れません！", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("金額は1円以上にしてください。", ephemeral=True)
        return

    view = InvoiceView(guild_id=interaction.guild_id, target_user=member, sender=interaction.user, amount=amount)
    
    await interaction.response.send_message(
        f"📄 {member.mention} さん宛に **{amount:,}円** の請求書を発行しました。",
        ephemeral=True
    )
    
    await interaction.channel.send(
        f"📄 {member.mention} さん宛に **{amount:,}円** の請求書が届きました！\n以下のボタンから選択してください（本人のみ押せます）。",
        view=view
    )


# --- 5. 一般管理者用コマンド（お金の操作のみ） ---

@bot.tree.command(name="addmoney", description="【管理者用】指定したユーザーにお金を付与します")
@app_commands.describe(member="対象のユーザー", amount="付与する金額")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_admin(interaction):
        await interaction.response.send_message("このコマンドを実行する権限がありません（管理者限定）。", ephemeral=True)
        return
    
    data = get_user(interaction.guild_id, member.id)
    data["money"] += amount
    await interaction.response.send_message(f"👑 管理者権限により、{member.mention} に **{amount:,}円** を付与しました。", ephemeral=True)

@bot.tree.command(name="takemoney", description="【管理者用】指定したユーザーからお金を強制没収します")
@app_commands.describe(member="対象のユーザー", amount="没収する金額")
async def takemoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_admin(interaction):
        await interaction.response.send_message("このコマンドを実行する権限がありません（管理者限定）。", ephemeral=True)
        return
    
    data = get_user(interaction.guild_id, member.id)
    data["money"] = max(0, data["money"] - amount)
    await interaction.response.send_message(f"👑 管理者権限により、{member.mention} から **{amount:,}円** を強制没収しました。", ephemeral=True)


# --- 6. ボット主（オーナー）専用コマンド（ロール管理 ＆ お金無限発行） ---

@bot.tree.command(name="role_create", description="【ボット主専用】新しいロールを作成します")
@app_commands.describe(
    name="ロールの名前", 
    color="色 (red, blue, green, gold, または #HEX)",
    admin_permission="管理者権限を付与するかどうか (True: する / False: しない)"
)
async def role_create(interaction: discord.Interaction, name: str, color: str = "default", admin_permission: bool = False):
    if not await is_owner(interaction):
        await interaction.response.send_message("このコマンドはボットの作成者（オーナー）しか実行できません！", ephemeral=True)
        return
    
    permissions = discord.Permissions(administrator=True) if admin_permission else discord.Permissions.none()

    discord_color = discord.Color.default()
    c = color.lower()
    if c == "red": discord_color = discord.Color.red()
    elif c == "blue": discord_color = discord.Color.blue()
    elif c == "green": discord_color = discord.Color.green()
    elif c == "gold": discord_color = discord.Color.gold()
    elif c.startswith("#"):
        try:
            discord_color = discord.Color(int(c.replace("#", ""), 16))
        except:
            pass

    try:
        new_role = await interaction.guild.create_role(name=name, color=discord_color, permissions=permissions)
        admin_text = "【管理者権限: あり】" if admin_permission else "【管理者権限: なし】"
        await interaction.response.send_message(f"✨ ロール `{new_role.name}` を作成しました！ {admin_text}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"ロールの作成に失敗しました（ボットの権限不足などの可能性があります）。", ephemeral=True)

@bot.tree.command(name="role_give", description="【ボット主専用】指定したユーザーにロールを付与します")
@app_commands.describe(member="対象のユーザー", role="付与するロール")
async def role_give(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not await is_owner(interaction):
        await interaction.response.send_message("このコマンドはボットの作成者（オーナー）しか実行できません！", ephemeral=True)
        return
    
    try:
        await member.add_roles(role)
        await interaction.response.send_message(f"✅ {member.mention} にロール `{role.name}` を付与しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"ロールの付与に失敗しました（ボットのロール位置が対象ロールより下にある可能性があります）。", ephemeral=True)

@bot.tree.command(name="role_remove", description="【ボット主専用】指定したユーザーからロールを剥奪します")
@app_commands.describe(member="対象のユーザー", role="剥奪するロール")
async def role_remove(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not await is_owner(interaction):
        await interaction.response.send_message("このコマンドはボットの作成者（オーナー）しか実行できません！", ephemeral=True)
        return
    
    try:
        await member.remove_roles(role)
        await interaction.response.send_message(f"❌ {member.mention} からロール `{role.name}` を剥奪しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"ロールの剥奪に失敗しました。", ephemeral=True)

@bot.tree.command(name="owner_add_money", description="【ボット主専用】無限にお金を出すチートコマンド")
@app_commands.describe(member="対象のユーザー", amount="付与する金額")
async def owner_add_money(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await is_owner(interaction):
        await interaction.response.send_message("このコマンドはボットの作成者（オーナー）しか実行できません！", ephemeral=True)
        return
    
    data = get_user(interaction.guild_id, member.id)
    data["money"] += amount
    await interaction.response.send_message(f"🛠️ [オーナー特権] {member.mention} に **{amount:,}円** を無限発行しました！", ephemeral=True)

if __name__ == "__main__":
  # 1. Flaskを裏で起動してRenderのポート監視をクリア
  keep_alive()
  # 2. Discordボットを起動
  bot.run(os.getenv("DISCORD_TOKEN"))
