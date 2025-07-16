package org.matsim.routing;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import picocli.CommandLine;

import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public class RoutingServer implements MATSimAppCommand {
    private static final int PORT = 50051;
    private static final Logger log = LogManager.getLogger(RoutingServer.class);

    private static final Pattern PATTERN = Pattern.compile("\\d+pct");

    // we are not using SampleOptions here because it does not accept double values like 0.1
    @CommandLine.Option(names = "--sample", description = "Sample options for the server")
    private String sample;

    @CommandLine.Option(names = "--config", description = "Path to config", required = true)
    private String config;

    @CommandLine.Option(names = "--output", description = "Base output directory for the server", required = true)
    private String output;

    @CommandLine.Option(names = "--threads", description = "Number of threads to use for routing")
    private int numThreads = 1;

    public static void main(String[] args) throws IOException, InterruptedException {
        new RoutingServer().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        log.info("Starting server with sample: {}, config: {}, output: {}, threads: {}", sample, config, output, numThreads);

        Config config = ConfigUtils.loadConfig(this.config);

        if (sample != null) {
            config.plans().setInputFile(adjustName(config.plans().getInputFile()));
        }

        config.controller().setOutputDirectory(output);

        RoutingService routingService = new RoutingService.Factory(config).create();
        Server server = ServerBuilder.forPort(PORT)
                .addService(routingService)
                .addService(ProtoReflectionService.newInstance())
                .executor(Executors.newFixedThreadPool(numThreads))
                .build()
                .start();

        log.info("Server started on port {}", PORT);
        server.awaitTermination();

        return 0;
    }

    private String adjustName(String name) {
        String postfix = this.sample + "pct";

        return PATTERN.matcher(name).replaceAll(postfix);
    }
}
