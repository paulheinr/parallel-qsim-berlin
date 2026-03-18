use clap::Parser;
use rust_qsim::external_services::routing::RoutingServiceAdapterFactory;
use rust_qsim::external_services::{
    AdapterHandle, AdapterHandleBuilder, AsyncExecutor, ExternalServiceType,
};
use rust_qsim::simulation::agents::agent::SimulationAgent;
use rust_qsim::simulation::agents::agent_logic::AdaptivePlanBasedSimulationLogic;
use rust_qsim::simulation::agents::{
    AgentEvent, EnvironmentalEventObserver, SimulationAgentLogic, SimulationAgentState,
};
use rust_qsim::simulation::config::{CommandLineArgs, Config, RoutingMode};
use rust_qsim::simulation::controller::controller::ControllerBuilder;
use rust_qsim::simulation::controller::ExternalServices;
use rust_qsim::simulation::id::Id;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::population::agent_source::AgentSource;
use rust_qsim::simulation::scenario::network::Link;
use rust_qsim::simulation::scenario::population::{
    InternalActivity, InternalLeg, InternalPerson, PREPLANNING_HORIZON,
};
use rust_qsim::simulation::scenario::vehicles::InternalVehicleType;
use rust_qsim::simulation::scenario::{trip_structure_utils, MutableScenario, ScenarioPartition};
use rust_qsim::simulation::time_queue::{EndTime, Identifiable};
use std::collections::HashMap;
use std::sync::{Arc, Barrier};
use tracing::info;

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
struct BerlinCommandLineArgs {
    #[clap(flatten)]
    delegate: CommandLineArgs,
    #[clap(long)]
    horizon: Option<usize>,
    #[clap(long, short, num_args = 1.., value_delimiter = ' ')]
    router_ip: Option<Vec<String>>,
}

fn main() {
    let _g = init_std_out_logging_thread_local();

    let args = BerlinCommandLineArgs::parse();

    info!("Starting Berlin example with args: {:?}", args);

    // load config
    let config = Arc::new(Config::from_args(args.delegate));

    // load scenario
    let mut scenario = MutableScenario::load(config.clone());

    add_teleported_vehicle(&mut scenario, "walk");
    add_teleported_vehicle(&mut scenario, "pt");
    add_dummy_link(&mut scenario);
    if let Some(horizon) = args.horizon {
        info!("Adapting the preplanning horizon.");
        add_preplanning_horizon(&mut scenario, horizon);
    }

    // create controller
    let mut builder = ControllerBuilder::default_with_scenario(scenario);
    builder = builder.agent_source(MyAgentSource);

    let (service, barrier, adapter) = if let Some(ips) = args.router_ip {
        create_router_adapter(&config, ips)
    } else {
        (None, None, None)
    };

    builder = if let Some(service) = service {
        builder.external_services(service)
    } else {
        builder
    };

    builder = if let Some(barrier) = barrier {
        builder.global_barrier(barrier)
    } else {
        builder
    };

    builder = if let Some(adapter) = adapter {
        builder.adapter_handles(adapter)
    } else {
        builder
    };

    // run controller
    builder.build().unwrap().run();
}

struct MyAgentSource;

impl AgentSource for MyAgentSource {
    fn create_agents(
        &self,
        scenario: &mut ScenarioPartition,
    ) -> HashMap<Id<InternalPerson>, SimulationAgent> {
        // take Persons and copy them into queues. This way we can keep the population around to translate
        // ids for events processing...
        let persons = std::mem::take(&mut scenario.population.persons);
        let mut agents = HashMap::with_capacity(persons.len());

        for (id, person) in persons {
            Self::identify_logic_and_insert(&mut agents, id, person, &scenario.config);
        }
        agents
    }
}

impl MyAgentSource {
    fn identify_logic_and_insert(
        agents: &mut HashMap<Id<InternalPerson>, SimulationAgent>,
        id: Id<InternalPerson>,
        person: InternalPerson,
        config: &Config,
    ) {
        if config.routing().mode == RoutingMode::UsePlans {
            agents.insert(id, SimulationAgent::new_plan_based(person));
            return;
        }

        // go through all attributes of person's legs and check whether there is some marked as rolling horizon logic
        let has_at_least_one_preplanning_horizon = person
            .selected_plan()
            .as_ref()
            .unwrap_or_else(|| panic!("Plan does not exist for person with id: {}", id.external()))
            .acts()
            .iter()
            .any(|l| l.attributes.get::<u32>(PREPLANNING_HORIZON).is_some());

        if has_at_least_one_preplanning_horizon {
            let delegate = AdaptivePlanBasedSimulationLogic::new(person);
            let agent = SimulationAgent::new(Box::new(MinActivityTimeLogic::new(5 * 60, delegate)));
            agents.insert(id, agent);
        } else {
            // if there is no rolling horizon logic, we assume that the person has a plan logic
            // and we create a InternalSimulationAgent with plan logic
            agents.insert(id, SimulationAgent::new_plan_based(person));
        }
    }
}

struct MinActivityTimeLogic {
    time: u32, // seconds
    delegate: AdaptivePlanBasedSimulationLogic,
}

impl MinActivityTimeLogic {
    fn new(time: u32, delegate: AdaptivePlanBasedSimulationLogic) -> Self {
        Self { time, delegate }
    }
}

impl EndTime for MinActivityTimeLogic {
    fn end_time(&self, now: u32) -> u32 {
        let delegate_time = self.delegate.end_time(now);
        match self.state() {
            SimulationAgentState::LEG => delegate_time,
            SimulationAgentState::ACTIVITY => {
                if delegate_time < self.time {
                    self.time
                } else {
                    delegate_time
                }
            }
            SimulationAgentState::STUCK => {
                panic!("Agent got stuck")
            }
        }
    }
}

impl Identifiable<InternalPerson> for MinActivityTimeLogic {
    fn id(&self) -> &Id<InternalPerson> {
        self.delegate.id()
    }
}

impl EnvironmentalEventObserver for MinActivityTimeLogic {
    fn notify_event(&mut self, event: &mut AgentEvent, now: u32) {
        self.delegate.notify_event(event, now);
    }
}

impl SimulationAgentLogic for MinActivityTimeLogic {
    fn curr_act(&self) -> &InternalActivity {
        self.delegate.curr_act()
    }

    fn next_act(&self) -> &InternalActivity {
        self.delegate.next_act()
    }

    fn curr_leg(&self) -> &InternalLeg {
        self.delegate.curr_leg()
    }

    fn next_leg(&self) -> Option<&InternalLeg> {
        self.delegate.next_leg()
    }

    fn advance_plan(&mut self) {
        self.delegate.advance_plan()
    }

    fn state(&self) -> SimulationAgentState {
        self.delegate.state()
    }

    fn is_wanting_to_arrive_on_current_link(&self) -> bool {
        self.delegate.is_wanting_to_arrive_on_current_link()
    }

    fn curr_link_id(&self) -> Option<&Id<Link>> {
        self.delegate.curr_link_id()
    }

    fn peek_next_link_id(&self) -> Option<&Id<Link>> {
        self.delegate.peek_next_link_id()
    }

    fn wakeup_time(&self, now: u32) -> u32 {
        self.delegate.wakeup_time(now)
    }
}

fn create_router_adapter(
    config: &Arc<Config>,
    ips: Vec<String>,
) -> (
    Option<ExternalServices>,
    Option<Arc<Barrier>>,
    Option<Vec<AdapterHandle>>,
) {
    // Creating the routing adapter is only one task, so we add 1 and not the number of worker threads!
    let total_thread_count = config.partitioning().num_parts + 1;
    let barrier = Arc::new(Barrier::new(total_thread_count as usize));

    // Configuring the routing adapter. We need
    // - the IP address of the router service
    // - the configuration of the simulation
    // - the shutdown handles of the executor (= receiver of shutdown signals from the controller)
    // The AsyncExecutor will spawn a thread for the routing service adapter and an async runtime.
    let executor = AsyncExecutor::from_config(&config, barrier.clone());
    let factory =
        RoutingServiceAdapterFactory::new(ips, config.clone(), executor.shutdown_handles());

    // Spawning the routing service adapter in a separate thread. The adapter will be run in its own tokio runtime.
    // This function returns
    // - the join handle of the adapter thread
    // - a channel for sending requests to the adapter
    // - a channel for sending shutdown signal for the adapter
    let (router_handle, send, send_sd) = executor.spawn_thread("router", factory);

    // Creating the adapter handle. This is necessary for regulated shutdown of the adapter thread. Otherwise, the adapter might be stuck in a loop.
    let adapters = vec![
        AdapterHandleBuilder::default()
            .shutdown_sender(send_sd)
            .handle(router_handle)
            .build()
            .unwrap(),
    ];

    // The request sender is passed to the controller.
    let mut services = ExternalServices::default();
    services.insert(ExternalServiceType::Routing("pt".into()), send.into());
    (Some(services), Some(barrier), Some(adapters))
}

fn add_preplanning_horizon(scenario: &mut MutableScenario, horizon: usize) {
    for (_, person) in &mut scenario.population.persons {
        let spans =
            trip_structure_utils::get_trip_spans_default(&person.selected_plan().unwrap().elements);
        for span in spans {
            let elements = span.trip_elements(&person.selected_plan().unwrap().elements);
            let mode = trip_structure_utils::identify_main_mode(elements)
                .expect("could not identify main mode");
            if mode.eq("pt") {
                span.origin_mut(&mut person.selected_plan_mut().elements)
                    .attributes
                    .insert(PREPLANNING_HORIZON, horizon);
            }
        }
    }
}

// Adds a dummy link between PT and car network at Gotzkowskybrücke
fn add_dummy_link(scenario: &mut MutableScenario) {
    let partition = scenario
        .network
        .get_node(&Id::get_from_ext("pt_648553_bus"))
        .partition;

    scenario.network.add_link(Link {
        id: Id::create("pt-connection"),
        from: Id::get_from_ext("pt_648553_bus"),
        to: Id::get_from_ext("cluster_1807917065_1929624603_1929624605_29962151_#3more"),
        length: 1.0,
        capacity: 0.0,
        freespeed: 0.0,
        permlanes: 1.0,
        modes: Default::default(),
        partition,
        attributes: Default::default(),
    });
}

fn add_teleported_vehicle(scenario: &mut MutableScenario, mode: &str) {
    let id = Id::create(mode);
    scenario.garage.vehicle_types.insert(
        id.clone(),
        InternalVehicleType {
            id,
            length: 1.,
            width: 1.,
            max_v: 1.23,
            pce: 0.1,
            fef: 0.0,
            net_mode: Id::create(mode),
            attributes: Default::default(),
        },
    );

    scenario.population.persons.keys().for_each(|id| {
        scenario.garage.vehicles.insert(
            Id::create(&format!("{}_{}", id, mode)),
            rust_qsim::simulation::scenario::vehicles::InternalVehicle {
                id: Id::create(&format!("{}-{}", id, mode)),
                max_v: 0.833,
                pce: 0.1,
                vehicle_type: Id::create(mode),
                attributes: Default::default(),
            },
        );
    });
}
