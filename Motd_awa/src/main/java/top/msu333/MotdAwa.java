package top.msu333;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.server.MinecraftServer;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class MotdAwa implements ModInitializer {

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
    private static final Path CONFIG_FILE = FabricLoader.getInstance().getConfigDir().resolve("motd_awa.json");
    private final Random random = new Random();
    private ConfigData config;
    private MinecraftServer server;
    private long lastUpdateTime = 0;

    public static class ConfigData {
        public List<String> motdList = new ArrayList<>(List.of(
                "§cM§6S§eU   §a3.0  §bBeta  §d2.0  §5Pre-2\n§7彩虹服务器",
                "§4§lM§c§lS§6§lU §e§l3.0 §a§lBeta §b§l2.0 §d§lPre-2\n§f欢迎来到 §k彩虹世界§r",
                "§d§l★ §b§lMSU §e§l3.0 §a§lBeta §6§l2.0 §c§lPre-2 §d§l★\n§7彩虹效果"
        ));
        public boolean enableRandomMotd = true;
        public int updateIntervalSeconds = 2;
    }

    @Override
    public void onInitialize() {
        loadConfig();

        System.out.println("§a[MotdAwa] 模组已加载！共 " + config.motdList.size() + " 条 MOTD 可用");

        ServerLifecycleEvents.SERVER_STARTING.register(server -> {
            this.server = server;
            updateMotd();
        });

        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (this.server == null) {
                this.server = server;
            }

            if (config.enableRandomMotd && config.motdList != null && !config.motdList.isEmpty()) {
                long currentTime = System.currentTimeMillis();
                if (lastUpdateTime == 0) {
                    lastUpdateTime = currentTime;
                }

                if (currentTime - lastUpdateTime >= config.updateIntervalSeconds * 1000) {
                    lastUpdateTime = currentTime;
                    updateMotd();
                }
            }
        });

        System.out.println("§a[MotdAwa] 动态 MOTD 已启用！每 " + config.updateIntervalSeconds + " 秒自动随机更换一次");
    }

    /**
     * 将文本转换为彩虹色（每个字符不同颜色）
     */
    private String rainbowText(String text, boolean bold) {
        String[] colors = {"§c", "§6", "§e", "§a", "§b", "§9", "§d", "§5"};
        StringBuilder result = new StringBuilder();
        int colorIndex = 0;

        for (char c : text.toCharArray()) {
            if (c == ' ') {
                result.append(' ');
                continue;
            }
            result.append(colors[colorIndex % colors.length]);
            if (bold) result.append("§l");
            result.append(c);
            colorIndex++;
        }
        return result.toString();
    }

    private void updateMotd() {
        if (server == null) return;

        int index = random.nextInt(config.motdList.size());
        String rawMotd = config.motdList.get(index);

        // 检测是否需要彩虹效果
        if (rawMotd.contains("<rainbow>")) {
            String text = rawMotd.replace("<rainbow>", "").replace("</rainbow>", "");
            rawMotd = rainbowText(text, true);
        }

        String motd = rawMotd.replace("\\n", "\n");
        server.setMotd(motd);
    }

    private void loadConfig() {
        try {
            if (Files.exists(CONFIG_FILE)) {
                config = GSON.fromJson(Files.readString(CONFIG_FILE), ConfigData.class);
            } else {
                config = new ConfigData();
                Files.writeString(CONFIG_FILE, GSON.toJson(config));
            }
        } catch (IOException e) {
            config = new ConfigData();
        }
    }
}