fn main() {
    #[cfg(target_os = "macos")]
    println!("cargo:rustc-link-arg=-undefined");
    #[cfg(target_os = "macos")]
    println!("cargo:rustc-link-arg=dynamic_lookup");
}
