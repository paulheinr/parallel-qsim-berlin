package org.matsim.analysis;

import com.google.common.util.concurrent.ListenableFuture;
import com.google.protobuf.Empty;
import io.grpc.ConnectivityState;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.matsim.application.MATSimAppCommand;
import picocli.CommandLine;
import routing.Routing;
import routing.RoutingServiceGrpc;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class MockRoutingClient implements MATSimAppCommand {
    private final static int SIM_TIME = 36 * 60 * 60;

    @CommandLine.Option(names = "--requestsFile", description = "Path to requests file", defaultValue = "requests.pb")
    private String requestsFile;

    @CommandLine.Option(names = "--ip", description = "IP Address of the routing server", defaultValue = "localhost")
    private String ip;

    @CommandLine.Option(names = "--port", description = "Port of the routing server", defaultValue = "50051")
    private int port;

    public static void main(String[] args) {
        new MockRoutingClient().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        List<List<Routing.Request>> requests = readRequests(Path.of(requestsFile));

        ManagedChannel channel = ManagedChannelBuilder.forAddress(ip, port).usePlaintext().build();

        System.out.println("Waiting for gRPC channel to become READY...");
        waitForReady(channel, Duration.ofMinutes(5));
        System.out.println("gRPC channel is READY.");

        RoutingServiceGrpc.RoutingServiceFutureStub service = RoutingServiceGrpc.newFutureStub(channel);

        List<List<ListenableFuture<Routing.Response>>> openFuturesByDeparture = new ArrayList<>(SIM_TIME);

        for (int i = 0; i < SIM_TIME; i++) {
            openFuturesByDeparture.add(new ArrayList<>(50));
        }

        int now = 0;
        while (now < SIM_TIME) {
            if (now % 3600 == 0) {
                System.out.println("Processing now = " + now / 3600 + "h");
            }

            List<Routing.Request> currentRequests = requests.get(now);
            for (Routing.Request currentRequest : currentRequests) {
                int dep = currentRequest.getDepartureTime();
                ListenableFuture<Routing.Response> future = service.getRoute(currentRequest);
                openFuturesByDeparture.get(dep).add(future);
            }

            // process all open futures for now departures
            for (ListenableFuture<Routing.Response> future : openFuturesByDeparture.get(now)) {
                try {
                    future.get();
                    // process response if needed
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }

            now++;
        }

        ListenableFuture<Empty> shutdown = service.shutdown(Empty.newBuilder().build());
        shutdown.get();

        return 0;
    }

    private static List<List<Routing.Request>> readRequests(Path path) {
        System.out.println("Reading requests from " + path);
        List<Routing.Request> messages = new LinkedList<>();

        try (InputStream in = Files.newInputStream(path)) {
            Routing.Request msg;
            while ((msg = Routing.Request.parseDelimitedFrom(in)) != null) {
                messages.add(msg);
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }

        System.out.println("Read " + messages.size() + " requests");

        messages.sort(Comparator.comparing(Routing.Request::getNow));

        List<List<Routing.Request>> res = new ArrayList<>(SIM_TIME);

        for (int i = 0; i < SIM_TIME; i++) {
            res.add(new ArrayList<>(50));
        }

        int now = 0;
        for (Routing.Request message : messages) {
            if (message.getNow() < now) {
                throw new IllegalStateException("Messages are not sorted by now");
            } else if (message.getNow() == now) {
                res.get(now).add(message);
            } else {
                now = message.getNow();
                res.get(now).add(message);
            }
        }


        return res;
    }

    private static void waitForReady(ManagedChannel channel, Duration timeout) throws InterruptedException {

        long deadlineNanos = System.nanoTime() + timeout.toNanos();

        ConnectivityState state = channel.getState(true);

        while (state != ConnectivityState.READY) {
            long remainingNanos = deadlineNanos - System.nanoTime();
            if (remainingNanos <= 0) {
                throw new IllegalStateException("gRPC channel did not become READY within " + timeout);
            }

            channel.notifyWhenStateChanged(state, () -> {
            });

            // Wait briefly before re-checking
            TimeUnit.MILLISECONDS.sleep(100);
            state = channel.getState(false);
        }
    }
}
