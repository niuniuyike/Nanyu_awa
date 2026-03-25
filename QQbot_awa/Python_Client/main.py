import asyncio
import json
import os
import time
import random
import aiohttp
import websockets
import logging
import base64
from Crypto.Cipher import AES

# ================= 配置与日志 =================
WS_URL = "ws://127.0.0.1:3001"
DATA_FILE = "bot_data.json"
BACKUP_FILE = "bot_data.json.bak"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AwaBot")

# ================= 隐私解密工具 =================
def decrypt_data(encrypted_b64, key_str):
    """
    解密来自 Java 端的 AES-GCM 数据包
    """
    try:
        # 准备 Key (强制对齐 32 字节以适配 AES-256)
        key = key_str.encode('utf-8')[:32].ljust(32, b'\0')
        # Base64 解码
        combined = base64.b64decode(encrypted_b64)
        # 拆分 IV (12字节) 和 密文 (含 16 字节 TAG)
        iv = combined[:12]
        cipher_text_with_tag = combined[12:]
        tag = cipher_text_with_tag[-16:]
        cipher_text = cipher_text_with_tag[:-16]
        
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        decrypted_data = cipher.decrypt_and_verify(cipher_text, tag)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception as e:
        logger.error(f"解密失败，请检查密码是否一致: {e}")
        return None

# ================= 数据持久化 =================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"数据读取失败，尝试载入备份: {e}")
            if os.path.exists(BACKUP_FILE):
                with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
    return {"servers": {}, "users": {}}

def save_data(data):
    try:
        if os.path.exists(DATA_FILE):
            os.replace(DATA_FILE, BACKUP_FILE)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"数据保存失败: {e}")

# ================= 核心类 =================
class NapCatBot:
    def __init__(self):
        self.data = load_data()
        self.pending_binds = {}
        self.ws = None
        self.session = None

    async def send_msg(self, msg_type, target_id, text):
        if not self.ws or self.ws.closed: return
        try:
            payload = {
                "action": "send_msg",
                "params": {
                    "message_type": msg_type,
                    "message": text,
                    "group_id": target_id if msg_type == "group" else None,
                    "user_id": target_id if msg_type == "private" else None
                }
            }
            await self.ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.error(f"消息发送失败: {e}")

    def _is_player_visible(self, player_name):
        for uid, udata in self.data["users"].items():
            if udata.get("name") == player_name:
                return udata.get("state", 1) == 1
        return True

    async def _broadcast(self, cid, text):
        cfg = self.data["servers"].get(cid, {})
        if not cfg.get("message_on"): return
        disturb = cfg.get("disturb")
        if disturb:
            now = time.strftime("%H%M")
            start, end = disturb["start"], disturb["end"]
            if start <= end:
                if not (start <= now <= end): return
            else: 
                if not (now >= start or now <= end): return
        await self.send_msg(cfg.get("type", "group"), cid, text)

    async def poll_server_monitor(self):
        while True:
            now_ts = time.time()
            self.pending_binds = {k: v for k, v in self.pending_binds.items() if now_ts <= v["expire"]}

            for cid, cfg in list(self.data["servers"].items()):
                try:
                    headers = {"Authorization": cfg.get('pass', '')}
                    async with self.session.get(f"{cfg['url']}/server", headers=headers, timeout=5) as resp:
                        if resp.status == 200:
                            # 解密逻辑开始
                            pkg = await resp.json()
                            res_data = decrypt_data(pkg.get("data"), cfg.get('pass'))
                            if not res_data: raise Exception("Decrypt Error")
                            
                            # 处理绑定逻辑
                            binds = res_data.get("binds", {})
                            for mc_name, code in binds.items():
                                code_str = str(code)
                                if code_str in self.pending_binds:
                                    u_id = self.pending_binds[code_str]["qq"]
                                    user_info = self.data["users"].get(u_id, {"state": 1})
                                    user_info["name"] = mc_name
                                    self.data["users"][u_id] = user_info
                                    save_data(self.data)
                                    await self.send_msg("private", u_id, f"绑定成功了喵~！\n游戏ID: {mc_name}")
                                    del self.pending_binds[code_str]

                            # 处理播报逻辑
                            is_online = cfg.get("last_status", False)
                            current_players = res_data.get('players', [])
                            last_players = cfg.get("last_players", [])

                            if not is_online:
                                self.data["servers"][cid]["last_status"] = True
                                self.data["servers"][cid]["last_players"] = current_players
                                await self._broadcast(cid, "服务器重新上线了喵~")
                            else:
                                joined = set(current_players) - set(last_players)
                                left = set(last_players) - set(current_players)
                                for p in joined:
                                    if self._is_player_visible(p): await self._broadcast(cid, f"有猫猫进入了服务器！{p}")
                                for p in left:
                                    if self._is_player_visible(p): await self._broadcast(cid, f"{p} 退出了服务器")
                                
                                if joined or left:
                                    self.data["servers"][cid]["last_players"] = current_players
                            save_data(self.data)
                        else: raise Exception("API Error")
                except:
                    if cfg.get("last_status", False):
                        self.data["servers"][cid]["last_status"] = False
                        self.data["servers"][cid]["last_players"] = []
                        save_data(self.data)
                        await self._broadcast(cid, "服务器下线或超时")
            await asyncio.sleep(3)

    async def handle_message(self, data):
        if data.get("post_type") != "message": return
        msg = data.get("raw_message", "").strip()
        if not (msg.startswith("!") or msg.startswith("！")): return

        parts = msg[1:].split()
        if not parts: return
        cmd = parts[0].lower()
        
        sender_id = str(data.get("user_id"))
        msg_type = data.get("message_type")
        cid = str(data.get("group_id")) if msg_type == "group" else sender_id

        if cmd == "ping":
            await self.send_msg(msg_type, cid, "pong~")

        elif cmd == "help":
            help_msg = ("指令列表：\n!ping - 测试\n!link [地址] [密码]\n!unlink - 切断关联\n!bind - 绑定码\n!unbind - 解绑\n!state [1/2] - 在线/隐身\n!message [on/off] - 播报开关\n!disturb [开始] [结束]/none - 播报时间段\n!server - 查看状态")
            await self.send_msg(msg_type, cid, help_msg)

        elif cmd == "disturb":
            if cid not in self.data["servers"]:
                return await self.send_msg(msg_type, cid, "错误：请先关联服务器")
            
            if len(parts) < 2:
                return await self.send_msg(msg_type, cid, "用法: !disturb 0900 2300 或 !disturb none")
            
            sub_cmd = parts[1].lower()
            
            # 处理关闭逻辑
            if sub_cmd == "none":
                self.data["servers"][cid]["disturb"] = None
                save_data(self.data)
                return await self.send_msg(msg_type, cid, "已恢复全天播报")
            
            # 处理设置逻辑
            if len(parts) >= 3:
                start, end = parts[1], parts[2]
                
                # 校验格式：必须是4位数字，且小时位 00-24，分钟位 00-59
                def is_valid_time(t):
                    if len(t) != 4 or not t.isdigit():
                        return False
                    hour, minute = int(t[:2]), int(t[2:])
                    return 0 <= hour <= 24 and 0 <= minute <= 59

                if is_valid_time(start) and is_valid_time(end):
                    self.data["servers"][cid]["disturb"] = {"start": start, "end": end}
                    save_data(self.data)
                    await self.send_msg(msg_type, cid, f"已设置播报时间段为: {start} 到 {end}")
                else:
                    await self.send_msg(msg_type, cid, "格式错误喵！请输入4位数字（如 0900 2300），不要带冒号或汉字")
            else:
                await self.send_msg(msg_type, cid, "用法错误：设置时间段需要 [开始时间] 和 [结束时间]")

        elif cmd == "link":
            if len(parts) < 3: return await self.send_msg(msg_type, cid, "用法: !link [地址] [密码]")
            addr = parts[1] if parts[1].startswith("http") else f"http://{parts[1]}"
            if not addr.endswith("/api"): addr += "/api"
            try:
                # 关联时尝试解密 TPS 进行验证
                async with self.session.get(f"{addr}/tps", headers={"Authorization": parts[2]}, timeout=5) as resp:
                    if resp.status == 200:
                        pkg = await resp.json()
                        if decrypt_data(pkg.get("data"), parts[2]):
                            self.data["servers"][cid] = {"url": addr, "pass": parts[2], "type": msg_type, "message_on": False, "disturb": None, "last_players": [], "last_status": True}
                            save_data(self.data)
                            await self.send_msg(msg_type, cid, "服务器关联成功了喵~")
                        else: await self.send_msg(msg_type, cid, "关联失败：解密校验不通过")
                    else: await self.send_msg(msg_type, cid, f"关联失败: {resp.status}")
            except: await self.send_msg(msg_type, cid, "连接服务器失败")

        elif cmd == "unlink":
            if cid in self.data["servers"]:
                del self.data["servers"][cid]
                save_data(self.data)
                await self.send_msg(msg_type, cid, "已切断关联了喵~")
            else: await self.send_msg(msg_type, cid, "未关联任何服务器")

        elif cmd == "message":
            if cid not in self.data["servers"]:
                return await self.send_msg(msg_type, cid, "错误：请先关联服务器")
            if len(parts) < 2: return await self.send_msg(msg_type, cid, "用法: !message on/off")
            status = parts[1].lower() == "on"
            self.data["servers"][cid]["message_on"] = status
            save_data(self.data)
            await self.send_msg(msg_type, cid, f"进出播报已{'开启' if status else '关闭'}")

        elif cmd == "bind":
            if msg_type == "group": return await self.send_msg(msg_type, cid, "请私聊绑定喵~")
            code = str(random.randint(1000, 9999))
            self.pending_binds[code] = {"qq": sender_id, "expire": time.time() + 300}
            await self.send_msg("private", sender_id, f"验证码: {code}\n请在5分钟内游戏输入: /qqbot bind {code}，若无法绑定请在游戏中多试几次喵")

        elif cmd == "unbind":
            if sender_id in self.data["users"]:
                del self.data["users"][sender_id]
                save_data(self.data)
                await self.send_msg(msg_type, cid, "已解除账号绑定")
            else: await self.send_msg(msg_type, cid, "你尚未绑定账号")

        elif cmd == "state":
            if sender_id not in self.data["users"]: return await self.send_msg(msg_type, cid, "错误：请先绑定账号")
            if len(parts) < 2 or parts[1] not in ["1", "2"]: return await self.send_msg(msg_type, cid, "用法: !state 1(在线) 或 2(隐身)")
            self.data["users"][sender_id]["state"] = int(parts[1])
            save_data(self.data)
            await self.send_msg(msg_type, cid, f"状态更新为: {'在线' if parts[1]=='1' else '隐身'}")

        elif cmd in ["server", "player", "tps"]:
            cfg = self.data["servers"].get(cid)
            if not cfg: return await self.send_msg(msg_type, cid, "未关联服务器")
            try:
                ep = "tps" if cmd == "tps" else "server"
                async with self.session.get(f"{cfg['url']}/{ep}", headers={"Authorization": cfg['pass']}, timeout=5) as resp:
                    if resp.status == 200:
                        pkg = await resp.json()
                        d = decrypt_data(pkg.get("data"), cfg['pass'])
                        if not d: raise Exception("Decrypt Error")
                        
                        if ep == "tps": 
                            val = d.get('tps', 0.0)
                            # 格式化一下防止出现过长的小数
                            await self.send_msg(msg_type, cid, f"TPS: {val:.2f}")
                        else:
                            p = d.get('players', [])
                            await self.send_msg(msg_type, cid, f"现在有 {d.get('count')}只猫猫在游玩服务器\n猫猫列表: {', '.join(p) if p else '无'}")
                    else: await self.send_msg(msg_type, cid, f"查询失败: {resp.status}")
            except: await self.send_msg(msg_type, cid, "无法连接或解密失败")

    async def start(self):
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self.poll_server_monitor())
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    self.ws = ws
                    logger.info("已连接到 WebSocket")
                    while True:
                        msg = await ws.recv()
                        await self.handle_message(json.loads(msg))
            except Exception as e:
                self.ws = None
                logger.error(f"连接异常: {e}, 8秒后重试")
                await asyncio.sleep(8)

if __name__ == "__main__":
    bot = NapCatBot()
    try: asyncio.run(bot.start())
    except KeyboardInterrupt: pass