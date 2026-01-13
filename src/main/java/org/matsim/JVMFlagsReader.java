package org.matsim;

import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.util.List;

public class JVMFlagsReader {
    public static void main(String[] args) {
        RuntimeMXBean runtimeMxBean = ManagementFactory.getRuntimeMXBean();
        List<String> arguments = runtimeMxBean.getInputArguments();

        System.out.println("JVM Arguments:");
        for (String arg : arguments) {
            System.out.println(arg);
        }

        // Check for specific flag
        boolean useNUMA = arguments.stream()
                .anyMatch(arg -> arg.contains("UseNUMA"));
        System.out.println("\nUseNUMA flag present: " + useNUMA);
    }

    public static List<String> getJVMArguments() {
        RuntimeMXBean runtimeMxBean = ManagementFactory.getRuntimeMXBean();
        return runtimeMxBean.getInputArguments();
    }

    public static boolean isArgumentEnabled(String a) {
        return getJVMArguments().stream().anyMatch(arg -> arg.contains(a));
    }
}