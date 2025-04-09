package org.matsim.prepare;

import org.matsim.api.core.v01.Id;
import org.matsim.application.MATSimAppCommand;
import org.matsim.vehicles.*;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.Set;

@CommandLine.Command(
        name = "adapt-vehicle-types",
        description = "Adds a walk vehicle type to the vehicle types file and sets teleported modes."
)
public class AdaptVehicleTypes implements MATSimAppCommand {
    @CommandLine.Option(names = "--input", description = "Path to the input vehicle types file", required = true)
    private Path input;

    @CommandLine.Option(names = "--teleported-modes", description = "Teleported modes.", split = ",", required = true)
    private Set<String> teleportedModes;

    @Override
    public Integer call() throws Exception {
        Vehicles vehiclesContainer = VehicleUtils.createVehiclesContainer();
        MatsimVehicleReader vehicleReader = new MatsimVehicleReader(vehiclesContainer);
        vehicleReader.readFile(input.toString());

        VehicleType vehType = VehicleUtils.createVehicleType(Id.create("walk", VehicleType.class));
        vehType.setMaximumVelocity(1.23)
                .setPcuEquivalents(0.1)
                .setNetworkMode("walk")
                .setFlowEfficiencyFactor(10.0)
                .getAttributes().putAttribute("lod", "teleported");
        vehiclesContainer.addVehicleType(vehType);

        teleportedModes.forEach(mode -> {
            vehiclesContainer.getVehicleTypes().get(Id.create(mode, VehicleType.class)).getAttributes().putAttribute("lod", "teleported");
        });

        MatsimVehicleWriter vehicleWriter = new MatsimVehicleWriter(vehiclesContainer);
        String output = input.toString().replace(".xml", "-including-walk.xml");
        vehicleWriter.writeFile(output);

        return 0;
    }
}
