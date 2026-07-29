fn main() {
    rust_qsim::simulation::events::utils::compare_xml_event_files(
        "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/0.1pct/base-0/output_events.xml.zst",
        "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/0.1pct/base-1/output_events.xml.zst",
    )
    .unwrap();
}
