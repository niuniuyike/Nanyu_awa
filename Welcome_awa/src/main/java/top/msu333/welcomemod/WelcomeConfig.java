package top.msu333.welcomemod;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WelcomeConfig {
    private static final Logger LOGGER = LoggerFactory.getLogger("WelcomeMod");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Path CONFIG_PATH = FabricLoader.getInstance().getConfigDir().resolve("welcome-mod.json");

    private String welcomeMessage = "&a欢迎 &e%player% &a加入服务器！\n&6&l>>&r &b祝你游戏愉快 &6&l<<";

    public WelcomeConfig() {
    }

    public String getWelcomeMessage() {
        return welcomeMessage;
    }

    public static WelcomeConfig load() {
        if (Files.exists(CONFIG_PATH)) {
            try {
                // 使用 UTF-8 编码读取文件
                String json = Files.readString(CONFIG_PATH, StandardCharsets.UTF_8);
                WelcomeConfig config = GSON.fromJson(json, WelcomeConfig.class);
                LOGGER.info("Configuration loaded from: {}", CONFIG_PATH);
                return config;
            } catch (IOException e) {
                LOGGER.error("Failed to read config, using default", e);
            }
        }

        WelcomeConfig defaultConfig = new WelcomeConfig();
        defaultConfig.save();
        LOGGER.info("Created default config: {}", CONFIG_PATH);
        return defaultConfig;
    }

    public void save() {
        try {
            Files.createDirectories(CONFIG_PATH.getParent());
            String json = GSON.toJson(this);
            // 使用 UTF-8 编码写入文件
            Files.writeString(CONFIG_PATH, json, StandardCharsets.UTF_8);
        } catch (IOException e) {
            LOGGER.error("Failed to save config", e);
        }
    }
}