package org.matsim.routing;

import ch.sbb.matsim.config.SwissRailRaptorConfigGroup;
import ch.sbb.matsim.routing.pt.raptor.RaptorTimetableProvider;
import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptor;
import com.google.inject.Injector;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.protobuf.services.ProtoReflectionServiceV1;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Scenario;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.ControlerDefaultsModule;
import org.matsim.core.controler.NewControlerModule;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.controler.corelisteners.ControlerDefaultCoreListenersModule;
import org.matsim.core.scenario.ScenarioByInstanceModule;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.schemas.services.routing.v1.RoutingServiceGrpc;
import org.matsim.schemas.services.routing.v1.TimetableServiceGrpc;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * gRPC routing server for the Rust simulation, see the routing API {@code matsim/services/routing/v1/routing.proto} of matsim-schemas.
 * <p>
 * Loads the scenario of a MATSim config (network, transit schedule, vehicles; no plans), creates one pt
 * router per worker thread and only then opens the port, so a connection means the server is ready. The
 * standard gRPC health service reports {@code SERVING} from then on. The server stops on the
 * {@code Shutdown} call of a client or when the JVM is terminated.
 * <p>
 * With {@code useTimetableUpdates} in the config group {@code swissRailRaptor}, the server also receives the timetable
 * stream ({@code TimetableService}). The server creates both services next to each other: the
 * {@link TimetableUpdateService} fills the {@link TimetableVersions}, the {@link RoutingService} reads them.
 */
@Command(name = "matsim-rust-router", mixinStandardHelpOptions = true,
        description = "Answers routing requests of matsim-rust with MATSim's pt router.")
public final class RoutingServer implements MATSimAppCommand {
    private static final Logger log = LogManager.getLogger(RoutingServer.class);

    @Option(names = "--config", required = true,
            description = "MATSim config with network, transit schedule and routing parameters. Plans and counts are not read.")
    private String config;

    @Option(names = "--output", defaultValue = RoutingUtils.DEFAULT_OUTPUT, description = "Output directory (default: ${DEFAULT-VALUE}).")
    private Path output;

    @Option(names = "--threads", defaultValue = "" + RoutingUtils.DEFAULT_THREADS, description = "Number of routing threads (default: ${DEFAULT-VALUE}).")
    private int threads;

    @Option(names = "--port", defaultValue = "" + RoutingUtils.DEFAULT_PORT, description = "Port to listen on, 0 for any free port (default: ${DEFAULT-VALUE}).")
    private int port;

    public static void main(String[] args) {
        new RoutingServer().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        log.info("Starting router with config {}, output {}, {} threads, port {}", config, output, threads, port);
        Config matsimConfig = prepareConfig(ConfigUtils.loadConfig(config), output);

        Running router = start(matsimConfig, port, threads);
        Runtime.getRuntime().addShutdownHook(new Thread(router::stop, "router-jvm-shutdown"));
        router.awaitTermination();
        log.info("Router stopped");
        return 0;
    }

    /**
     * Adapts a MATSim config for the router: no plans and counts, single-threaded MATSim internals (the
     * routers are thread locals), and the given output directory.
     */
    static Config prepareConfig(Config config, Path output) throws IOException {
        Files.createDirectories(output);
        config.controller().setOutputDirectory(output.toString());
        config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.overwriteExistingFiles);
        config.global().setNumberOfThreads(1);
        config.plans().setInputFile(null);
        config.counts().setInputFile(null);
        return config;
    }

    /**
     * Loads the scenario, creates the routers of all {@code threads} worker threads and starts the server on all
     * addresses at {@code port}. Returns once the server accepts requests.
     */
    static Running start(Config config, int port, int threads) throws IOException, InterruptedException, ExecutionException {
        return start(config, new InetSocketAddress(port), threads);
    }

    /**
     * Like {@link #start(Config, int, int)}, but on {@code address}. Tests bind to the loopback address: with port 0
     * on all addresses, the system may pick a port that another process holds on 127.0.0.1, and a client of localhost
     * then reaches that process instead of the router.
     */
    static Running start(Config config, InetSocketAddress address, int threads) throws IOException, InterruptedException, ExecutionException {
        AtomicReference<Running> running = new AtomicReference<>();
        Services services = createServices(config, () -> running.get().stop());
        ExecutorService executor = createExecutor(services.routing(), threads);
        services.routing().useRoutingExecutor(executor);
        HealthStatusManager health = new HealthStatusManager();

        ServerBuilder<?> builder = NettyServerBuilder.forAddress(address)
                .addService(services.routing())
                .addService(health.getHealthService())
                .addService(ProtoReflectionServiceV1.newInstance())
                .executor(executor);
        services.timetable().ifPresent(builder::addService);
        Server server = builder.build().start();
        running.set(new Running(server, executor, health));
        health.setStatus("", ServingStatus.SERVING);
        health.setStatus(RoutingServiceGrpc.SERVICE_NAME, ServingStatus.SERVING);
        if (services.timetable().isPresent()) {
            health.setStatus(TimetableServiceGrpc.SERVICE_NAME, ServingStatus.SERVING);
        }

        log.info("Router listening on port {}", server.getPort());
        return running.get();
    }

    /**
     * The gRPC services of a router: the routing service, and with timetable updates the receiver of the timetable
     * stream. Both share only the {@link TimetableVersions}.
     */
    record Services(RoutingService routing, Optional<TimetableUpdateService> timetable) {
    }

    /**
     * Loads the scenario of {@code config} (network, transit schedule, ...) and creates the services. With timetable
     * updates, the timetable versions are built on the data of the raptors of the injector: its factory caches the
     * data, so all routers and the versions use the same instance. {@code onShutdown} runs, in a new thread, when a
     * client calls {@code Shutdown}.
     */
    static Services createServices(Config config, Runnable onShutdown) {
        Scenario scenario = ScenarioUtils.loadScenario(config);
        Injector injector = createInjector(scenario);
        TimetableVersions versions = null;
        if (ConfigUtils.addOrGetModule(config, SwissRailRaptorConfigGroup.class).isUseTimetableUpdates()) {
            versions = new TimetableVersions(injector.getInstance(SwissRailRaptor.class).getUnderlyingData());
        }
        log.info("Timetable updates are {}", versions == null ? "off" : "on");
        return new Services(new RoutingService(injector, versions, onShutdown),
                versions == null ? Optional.empty() : Optional.of(new TimetableUpdateService(versions)));
    }

    /**
     * The injector of {@link org.matsim.core.controler.ControllerUtils#createAdhocInjector}, with the
     * {@link RequestTimetableProvider}, which routes a request on the version in its routing attributes.
     */
    static Injector createInjector(Scenario scenario) {
        return org.matsim.core.controler.Injector.createInjector(scenario.getConfig(), AbstractModule.override(
                List.of(new NewControlerModule(), new ControlerDefaultCoreListenersModule(), new ControlerDefaultsModule(), new ScenarioByInstanceModule(scenario)),
                new AbstractModule() {
                    @Override
                    public void install() {
                        bind(RaptorTimetableProvider.class).toInstance(new RequestTimetableProvider());
                    }
                }));
    }

    /**
     * A fixed pool whose threads each create their router before the server starts. A fixed pool starts a
     * new thread for every task until it has all of its threads, so each thread runs exactly one init.
     */
    private static ExecutorService createExecutor(RoutingService service, int threads)
            throws InterruptedException, ExecutionException {
        log.info("Initializing {} routing threads", threads);
        AtomicInteger counter = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(threads,
                r -> new Thread(r, "router-" + counter.getAndIncrement()));
        List<Future<?>> inits = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            inits.add(executor.submit(service::init));
        }
        for (Future<?> init : inits) {
            init.get();
        }
        return executor;
    }

    /**
     * A started router.
     */
    static final class Running {
        private final Server server;
        private final ExecutorService executor;
        private final HealthStatusManager health;

        private Running(Server server, ExecutorService executor, HealthStatusManager health) {
            this.server = server;
            this.executor = executor;
            this.health = health;
        }

        int port() {
            return server.getPort();
        }

        /**
         * Stops accepting requests, lets running ones finish for up to {@link RoutingUtils#STOP_TIMEOUT_SECONDS} s and stops the worker threads.
         */
        synchronized void stop() {
            if (server.isShutdown()) {
                return;
            }
            log.info("Stopping router");
            health.enterTerminalState();
            server.shutdown();
            try {
                if (!server.awaitTermination(RoutingUtils.STOP_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                    server.shutdownNow();
                }
            } catch (InterruptedException e) {
                server.shutdownNow();
                Thread.currentThread().interrupt();
            }
            executor.shutdownNow();
        }

        void awaitTermination() throws InterruptedException {
            server.awaitTermination();
            executor.shutdown();
            executor.awaitTermination(RoutingUtils.STOP_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }
}
