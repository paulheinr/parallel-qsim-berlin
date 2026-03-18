use rust_qsim::simulation::io::xml::network::IONetwork;
use rust_qsim::simulation::scenario::network::Network;

fn main() {
    let io_network = IONetwork::from_file("");
    let _network = Network::from(io_network);
}
