package org.matsim.routing;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.utils.io.IOUtils;
import org.matsim.examples.ExamplesUtils;

import java.io.IOException;
import java.net.URL;

public class RoutingServer {
    private static final int PORT = 50051;
    private static final Logger log = LogManager.getLogger(RoutingServer.class);

    public static void main(String[] args) throws IOException, InterruptedException {
        URL ptScenarioURL = ExamplesUtils.getTestScenarioURL("pt-tutorial");
        Config config = ConfigUtils.loadConfig(IOUtils.extendUrl(ptScenarioURL, "0.config.xml"));

        RoutingService routingService = new RoutingService.Factory(config).create();
        Server server = ServerBuilder.forPort(PORT)
                .addService(routingService)
                .addService(ProtoReflectionService.newInstance())
                .build()
                .start();

        log.info("Server started on port {}", PORT);
        server.awaitTermination();
    }
}
