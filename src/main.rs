use clap::Parser;
use std::process::Command;

const FILENAME_TEMPLATE: &str = "{url-hostname} - {date-iso} - {page-title}.{filename-extension}";

const BROWSER_CANDIDATES: &[&str] = &[
    "chrome",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
];

#[derive(Parser)]
#[command(name = "capture")]
#[command(about = "Capture websites as HTML bookmarks")]
struct Cli {
    /// URL to capture
    url: String,

    /// Output filename (uses template if not provided)
    #[arg(short, long)]
    output: Option<String>,

    /// Browser executable path (auto-detected if not provided)
    #[arg(short, long)]
    browser: Option<String>,
}

fn find_browser() -> Option<String> {
    for candidate in BROWSER_CANDIDATES {
        if Command::new("which")
            .arg(candidate)
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
        {
            return Some(candidate.to_string());
        }
    }
    None
}

fn main() {
    let cli = Cli::parse();

    let browser = cli.browser.or_else(find_browser).unwrap_or_else(|| {
        eprintln!("No browser found. Tried: {}", BROWSER_CANDIDATES.join(", "));
        eprintln!("Specify one with --browser");
        std::process::exit(1);
    });

    println!("Capturing {}", cli.url);

    let mut cmd = Command::new("single-file");
    cmd.arg("--browser-executable-path").arg(&browser);

    if let Some(output) = &cli.output {
        cmd.arg(&cli.url).arg(output);
    } else {
        cmd.arg("--filename-template")
            .arg(FILENAME_TEMPLATE)
            .arg(&cli.url);
    }

    let status = cmd.status().expect("Failed to execute single-file");

    if status.success() {
        println!("Done");
    } else {
        eprintln!("single-file failed with status: {}", status);
        std::process::exit(1);
    }
}
