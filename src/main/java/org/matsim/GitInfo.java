package org.matsim;

import java.io.InputStream;
import java.util.Properties;

public final class GitInfo {

    private static final Properties PROPS = new Properties();

    static {
        try (InputStream in = GitInfo.class
                .getClassLoader()
                .getResourceAsStream("git.properties")) {
            if (in != null) {
                PROPS.load(in);
            }
        } catch (Exception e) {
            throw new IllegalStateException("Failed to load git.properties", e);
        }
    }

    public static String commitHash() {
        return PROPS.getProperty("git.commit.id.abbrev", "unknown");
    }

    public static String branch() {
        return PROPS.getProperty("git.branch", "unknown");
    }
}
