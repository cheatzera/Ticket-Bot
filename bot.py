import discord
from discord.ext import commands
import io
import asyncio
from datetime import datetime
import os

LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID") or 1461184588159254720)

ALLOWED_ROLE_IDS = set()
_raw_allowed = os.environ.get("1460882840018358417", "1460882840018358417")
if _raw_allowed:
    try:
        ALLOWED_ROLE_IDS = {int(x) for x in _raw_allowed.split(",") if x.strip()}
    except ValueError:
        ALLOWED_ROLE_IDS = set()

PURCHASES_LOG_CHANNEL_ID = 1461184588159254720
PENDING_PURCHASES = {}
PACKAGES = {
    "basico": {"label": "Básico", "emoji": "🔰", "price": 50.00},
    "premium": {"label": "Premium", "emoji": "💎", "price": 80.00},
}

PIX_CODES = {
    "basico": "00020126580014BR.GOV.BCB.PIX0136e2d82410-6b47-48c9-a982-711aeb22b1d6520400005303986540550.005802BR5921Gabriel Silva Rondeli6009SAO PAULO62140510ZX6YsnULhB6304B122",
    "premium": "00020126580014BR.GOV.BCB.PIX0136e2d82410-6b47-48c9-a982-711aeb22b1d6520400005303986540580.005802BR5921Gabriel Silva Rondeli6009SAO PAULO62140510gwHkClvX8b63047F8D"
}

PIX_CHAVE = "e2d82410-6b47-48c9-a982-711aeb22b1d6"
PIX_NOME = "gabriel silva rondeli"
PIX_CIDADE = "Sao Paulo"

def generate_pix_code(amount: float, txid: str) -> str:
    def crc16(data: str) -> int:
        crc = 0xFFFF
        for byte in data.encode('utf-8'):
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

    payload = "000201"
    payload += "010211"
    pix_key = f"0014BR.GOV.BCB.PIX0112{PIX_CHAVE}"
    payload += f"26{len(pix_key):02d}{pix_key}"
    payload += "52040000"
    payload += "5303986"
    if amount > 0:
        amount_str = f"{amount:.2f}"
        payload += f"54{len(amount_str):02d}{amount_str}"
    payload += "5802BR"
    payload += f"59{len(PIX_NOME):02d}{PIX_NOME}"
    payload += f"60{len(PIX_CIDADE):02d}{PIX_CIDADE}"
    if txid:
        txid_field = f"05{len(txid):02d}{txid}"
        payload += f"62{len(txid_field):02d}{txid_field}"
    crc = crc16(payload + "6304")
    payload += f"6304{crc:04X}"
    return payload



DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = 1460782542587429030 

CATEGORY_IDS = {
    "Compra": 1460879475532103838, 
    "Suporte": 1460891685092458577 
}

CUSTOM_MESSAGES = {
    "Compra": "🛒 **Pedido de Compra**\n\nDescreva o que você deseja contratar.",
    "Suporte": "🛠️ **Suporte Técnico**\n\nExplique seu problema com o máximo de detalhes."
}

CHANNEL_NAME_PREFIX = "ticket"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def create_channel_and_send(
    interaction: discord.Interaction,
    category_id: int,
    message: str,
    short_name: str
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message(
            "❌ Erro ao obter o servidor.",
            ephemeral=True
        )
        return

    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message(
            "❌ Categoria inválida.",
            ephemeral=True
        )
        return

    safe_user = interaction.user.name.lower().replace(" ", "-")[:12]
    channel_name = f"{CHANNEL_NAME_PREFIX}-{short_name}-{safe_user}"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )
    }

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket criado por {interaction.user}"
        )

        embed = discord.Embed(
            title="📨 Atendimento Iniciado",
            description=message,
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Usuário: {interaction.user}")

        await channel.send(
            content=interaction.user.mention,
            embed=embed
        )

        try:
            await channel.edit(topic=f"ticket_owner:{interaction.user.id}")
        except Exception:
            pass

        try:
            await channel.send(view=TicketControls(channel, interaction.user.id, short_name))
        except Exception:
            pass

        await interaction.response.send_message(
            f"✅ Canal criado: {channel.mention}",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Sem permissão para criar canais.",
            ephemeral=True
        )


class PersistentPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Comprar",
        emoji="🛒",
        style=discord.ButtonStyle.primary,
        custom_id="panel:Compra"
    )
    async def comprar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await create_channel_and_send(
            interaction,
            CATEGORY_IDS["Compra"],
            CUSTOM_MESSAGES["Compra"],
            "compra"
        )

    @discord.ui.button(
        label="Suporte",
        emoji="🛠️",
        style=discord.ButtonStyle.success,
        custom_id="panel:Suporte"
    )
    async def suporte(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await create_channel_and_send(
            interaction,
            CATEGORY_IDS["Suporte"],
            CUSTOM_MESSAGES["Suporte"],
            "suporte"
        )


class TicketControls(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, owner_id: int, ticket_type: str = None):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner_id = owner_id
        self.ticket_type = ticket_type
        for child in list(self.children):
            try:
                if getattr(child, "custom_id", "") == "ticket:quickbuy" and self.ticket_type != "compra":
                    child.disabled = True
            except Exception:
                pass

    @discord.ui.button(label="Concluir", style=discord.ButtonStyle.danger, custom_id="ticket:conclude")
    async def conclude(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed = False
        if interaction.user.guild_permissions.manage_channels:
            if ALLOWED_ROLE_IDS:
                user_role_ids = {r.id for r in interaction.user.roles}
                if user_role_ids & ALLOWED_ROLE_IDS:
                    allowed = True

        if not allowed:
            await interaction.response.send_message("Somente administradores com cargos autorizados podem concluir.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        msgs = []
        async for m in self.channel.history(limit=None, oldest_first=True):
            msgs.append(m)

        participants = {str(m.author.id) for m in msgs if m.author}

        lines = []
        for m in msgs:
            ts = m.created_at.isoformat() if m.created_at else ""
            author = f"{getattr(m.author, 'name', 'Unknown')}#{getattr(m.author, 'discriminator', '')} ({getattr(m.author, 'id', '')})"
            content = m.content or ""
            attachments = ""
            if m.attachments:
                attachments = " ".join([f"[Attachment: {a.filename} - {a.url}]" for a in m.attachments])
            lines.append(f"[{ts}] {author}: {content} {attachments}")

        transcript_text = (
            f"Channel: {self.channel.name} (ID: {self.channel.id})\n"
            f"Created at: {self.channel.created_at.isoformat() if self.channel.created_at else ''}\n"
            f"Closed at: {datetime.utcnow().isoformat()}Z\n"
            f"Participants (IDs): {', '.join(sorted(participants))}\n"
            f"Messages: {len(msgs)}\n\n"
            + "\n".join(lines)
        )

        bio = io.BytesIO(transcript_text.encode("utf-8"))
        file = discord.File(bio, filename=f"{self.channel.name}_transcript.txt")

        if LOG_CHANNEL_ID == 0:
            await interaction.followup.send("LOG_CHANNEL_ID não configurado. Configure a variável de ambiente LOG_CHANNEL_ID.", ephemeral=True)
            return

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID) or bot.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            await interaction.followup.send("Canal de log não encontrado. Verifique LOG_CHANNEL_ID.", ephemeral=True)
            return

        embed = discord.Embed(title="Transcrição de Ticket", color=discord.Color.blue())
        embed.add_field(name="Channel", value=f"{self.channel.mention} ({self.channel.id})", inline=False)
        embed.add_field(name="Closed by", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        embed.add_field(name="Participants", value=", ".join(sorted(participants)) or "Nenhum", inline=False)
        embed.add_field(name="Messages", value=str(len(msgs)), inline=False)
        embed.add_field(name="Closed at", value=datetime.utcnow().isoformat()+"Z", inline=False)

        try:
            await log_channel.send(embed=embed, file=file)
        except Exception as e:
            await interaction.followup.send(f"Erro ao enviar transcrição: {e}", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        await interaction.followup.send(
            f"Ticket concluído e transcrição enviada para {log_channel.mention}. O canal será excluído em 5 segundos.",
            ephemeral=True
        )

        try:
            close_embed = discord.Embed(
                title="✅ Atendimento Finalizado",
                description="Obrigado pelo contato! Seu atendimento foi concluído com sucesso.\n\nEste canal será fechado automaticamente em breve. Se precisar de mais ajuda no futuro, estamos à disposição! 😊",
                color=discord.Color.green()
            )
            await self.channel.send(embed=close_embed)
        except Exception:
            pass

        await asyncio.sleep(5)
        try:
            await self.channel.delete(reason=f"Ticket concluído por {interaction.user}")
        except Exception as e:
            print(f"Erro ao excluir canal {self.channel}: {e}")

    @discord.ui.button(label="Compra rápida", style=discord.ButtonStyle.secondary, custom_id="ticket:quickbuy", emoji="⚡")
    async def quickbuy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.ticket_type != "compra":
            await interaction.response.send_message("Este botão só funciona em canais de Compra.", ephemeral=True)
            return
        await interaction.response.send_message("Escolha um pacote:", view=PurchaseSelect(self.channel, interaction.user.id), ephemeral=True)


class PurchaseSelect(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, user_id: int):
        super().__init__(timeout=120)
        self.channel = channel
        self.user_id = user_id
        options = [
            discord.SelectOption(label="Básico", value="basico", description="R$50,00", emoji="🔰"),
            discord.SelectOption(label="Premium", value="premium", description="R$80,00", emoji="💎"),
        ]
        self.select = discord.ui.Select(placeholder="Escolha um pacote", min_values=1, max_values=1, options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Apenas quem abriu o menu pode escolher.", ephemeral=True)
            return
        choice = self.select.values[0]
        pkg = PACKAGES[choice]
        pix = PIX_CODES[choice]
        PENDING_PURCHASES.setdefault(self.channel.id, {})[interaction.user.id] = {
            "package": choice,
            "package_label": pkg["label"],
            "amount": pkg["price"],
            "pix": pix,
            "time": datetime.utcnow().isoformat() + "Z",
            "status_message_id": None,
            "pix_message_id": None,
        }
        await interaction.response.defer()
        embed = discord.Embed(
            title="💳 Pagamento via PIX",
            description=f"Você selecionou o pacote **{pkg['label']}** por **R${pkg['price']:.2f}**.\n\n**Recebedor:** {PIX_NOME}\n\nAqui está o código PIX para copiar e colar.\n\nApós o pagamento, envie uma **print do comprovante** neste chat para confirmação.",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Status", value="🌀 Aguardando comprovante", inline=False)
        status_message = await self.channel.send(embed=embed)
        PENDING_PURCHASES[self.channel.id][interaction.user.id]["status_message_id"] = status_message.id
        pix_message = await self.channel.send(pix)
        PENDING_PURCHASES[self.channel.id][interaction.user.id]["pix_message_id"] = pix_message.id
        try:
            log_ch = bot.get_channel(PURCHASES_LOG_CHANNEL_ID)
            if log_ch:
                embed = discord.Embed(title="Pedido de Compra Iniciado", color=discord.Color.gold())
                embed.add_field(name="User", value=f"{interaction.user} ({interaction.user.id})", inline=False)
                embed.add_field(name="Package", value=pkg["label"], inline=True)
                embed.add_field(name="Amount", value=f"R${pkg['price']:.2f}", inline=True)
                embed.add_field(name="PIX Code", value=pix, inline=False)
                embed.add_field(name="Channel", value=f"{self.channel.mention} ({self.channel.id})", inline=False)
                await log_ch.send(embed=embed)
        except Exception:
            pass


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)
    if message.author.bot:
        return
    ch = message.channel
    pending = PENDING_PURCHASES.get(ch.id, {})
    purchaser = pending.get(message.author.id)
    if purchaser and message.attachments:
        log_ch = bot.get_channel(PURCHASES_LOG_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(title="Compra concluída", color=discord.Color.green())
            embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
            embed.add_field(name="Package", value=purchaser["package_label"], inline=True)
            embed.add_field(name="Amount", value=f"R${purchaser['amount']:.2f}", inline=True)
            embed.add_field(name="PIX Code", value=purchaser["pix"], inline=False)
            embed.add_field(name="Channel", value=f"{ch.mention} ({ch.id})", inline=False)
            files = []
            for att in message.attachments:
                try:
                    files.append(await att.to_file())
                except Exception:
                    pass
            await log_ch.send(embed=embed, files=files)
        # Atualizar o embed de status
        status_message_id = purchaser.get("status_message_id")
        pix_message_id = purchaser.get("pix_message_id")
        if status_message_id:
            try:
                status_message = await ch.fetch_message(status_message_id)
                updated_embed = status_message.embeds[0]
                updated_embed.set_field_at(0, name="Status", value="✅ Confirmado", inline=False)
                updated_embed.color = discord.Color.green()
                await status_message.edit(embed=updated_embed)
                # Novo embed de espera
                wait_embed = discord.Embed(
                    title="⏳ Aguardando Atendimento",
                    description="Seu pagamento foi confirmado com sucesso! 🎉\n\nUm de nossos atendentes especializados entrará em contato pelo chat em alguns instantes para prosseguir com seu pedido.\n\nObrigado pela paciência! 😊",
                    color=discord.Color.dark_green()
                )
                await ch.send(embed=wait_embed)
            except Exception as e:
                print(f"Erro ao atualizar embed: {e}")
        if pix_message_id:
            try:
                pix_message = await ch.fetch_message(pix_message_id)
                await pix_message.delete()
            except Exception as e:
                print(f"Erro ao deletar mensagem PIX: {e}")
        try:
            del pending[message.author.id]
            if not pending:
                del PENDING_PURCHASES[ch.id]
        except Exception:
            pass

@bot.event
async def on_ready():
    bot.add_view(PersistentPanel())
    print(f"✅ Bot online: {bot.user} | ID: {bot.user.id}")
    refreshed = 0
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                async for msg in channel.history(limit=200):
                    if msg.author == bot.user:
                        is_panel_msg = False
                        if "Painel ativo" in (msg.content or ""):
                            is_panel_msg = True
                        elif msg.embeds:
                            try:
                                for e in msg.embeds:
                                    if e.title and "Painel de Atendimento" in e.title:
                                        is_panel_msg = True
                                        break
                            except Exception:
                                pass

                        if is_panel_msg:
                            try:
                                embed = discord.Embed(
                                    title="🖥️ Painel de Atendimento",
                                    description=(
                                        "Bem-vindo!\n\n"
                                        "Escolha uma opção abaixo para abrir um **canal exclusivo**:\n\n"
                                        "🛒 **Compra** — Serviços e otimizações\n"
                                        "🛠️ **Suporte** — Ajuda técnica\n\n"
                                        "⏱️ Atendimento rápido e organizado"
                                    ),
                                    color=discord.Color.blurple()
                                )
                                await msg.edit(embed=embed, view=PersistentPanel())
                                refreshed += 1
                            except discord.Forbidden:
                                print(f"Permissões insuficientes para editar mensagem em {channel} (guild: {guild}).")
                            except Exception as e:
                                print(f"Erro ao editar mensagem em {channel}: {e}")
            except discord.Forbidden:
                print(f"Sem permissão para acessar histórico de {channel} (guild: {guild}).")
            except Exception as e:
                print(f"Erro ao ler histórico de {channel}: {e}")
    print(f"Paineis atualizados: {refreshed}")


@bot.command(name="painel")
@commands.has_permissions(administrator=True)
async def painel(ctx: commands.Context):
    embed = discord.Embed(
        title="🖥️ Painel de Atendimento",
        description=(
            "Bem-vindo!\n\n"
            "Escolha uma opção abaixo para abrir um **canal exclusivo**:\n\n"
            "🛒 **Compra** — Serviços e otimizações\n"
            "🛠️ **Suporte** — Ajuda técnica\n\n"
            "⏱️ Atendimento rápido e organizado"
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(text="Sistema de Tickets")
    embed.set_thumbnail(
        url="https://i.imgur.com/6Y6ZKpF.png"
    )

    await ctx.send(embed=embed, view=PersistentPanel())

bot.run(DISCORD_TOKEN)