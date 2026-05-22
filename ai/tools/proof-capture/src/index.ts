#!/usr/bin/env node
/**
 * proof-capture — Deterministic artifact capture for the proof-dev pipeline.
 *
 * Used in autonomous/headless mode where the interactive browser tools
 * (Claude in Chrome, gif_creator) are unavailable. Produces the same
 * proof artifacts — PNGs, WebMs — that land in proof/ and get embedded
 * in PR bodies.
 *
 * Distinct from Playwright MCP (agent-controlled browser during active work).
 * This tool is for standardised, reproducible output at verification time.
 *
 * Commands:
 *   screenshot  Single PNG at a URL
 *   record      WebM video (optionally script-driven)
 *   flow        Multi-step scripted flow → numbered PNGs
 */

import { chromium, Browser, BrowserContext, Page } from 'playwright';
import { Command } from 'commander';
import * as path from 'path';
import * as fs from 'fs';

const program = new Command();

program
  .name('proof-capture')
  .description('Deterministic artifact capture for proof-dev pipeline (headless mode)')
  .version('1.0.0');

// ── Utilities ──────────────────────────────────────────────────────────────────

function parseViewport(viewport: string): { width: number; height: number } {
  const [w, h] = viewport.split('x').map(Number);
  if (!w || !h) {
    throw new Error(`Invalid viewport: ${viewport} — expected WxH e.g. 1280x800`);
  }
  return { width: w, height: h };
}

function ensureDir(filePath: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

type FlowStep = { name: string; action: (page: Page) => Promise<void> };

async function loadFlowScript(scriptPath: string): Promise<FlowStep[]> {
  const resolved = path.resolve(scriptPath);
  if (!fs.existsSync(resolved)) throw new Error(`Script not found: ${resolved}`);
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const mod = require(resolved);
  const steps: FlowStep[] = mod.default ?? mod.steps ?? mod;
  if (!Array.isArray(steps)) {
    throw new Error('Flow script must export an array of { name, action(page) } steps');
  }
  return steps;
}

async function withPage(
  opts: {
    viewport: string;
    noAnimations?: boolean;
    video?: { dir: string; size: { width: number; height: number } };
  },
  fn: (page: Page, context: BrowserContext, browser: Browser) => Promise<void>,
): Promise<void> {
  const viewport = parseViewport(opts.viewport);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport,
    reducedMotion: opts.noAnimations !== false ? 'reduce' : 'no-preference',
    ...(opts.video ? { recordVideo: opts.video } : {}),
  });
  try {
    const page = await context.newPage();
    await fn(page, context, browser);
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

async function navigateSafely(page: Page, url: string): Promise<void> {
  try {
    await Promise.race([
      page.goto(url, { waitUntil: 'networkidle' }),
      new Promise<void>((_, reject) =>
        setTimeout(() => reject(new Error('Navigation timeout after 30s')), 30_000),
      ),
    ]);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error(`Warning: ${msg} — capturing current state`);
  }
}

// ── screenshot ─────────────────────────────────────────────────────────────────

program
  .command('screenshot')
  .description('Capture a single PNG screenshot')
  .requiredOption('--url <url>', 'URL to capture')
  .requiredOption('--output <path>', 'Output PNG path')
  .option('--viewport <WxH>', 'Viewport dimensions', '1280x800')
  .option('--full-page', 'Capture full page height', false)
  .option('--wait-selector <selector>', 'Wait for CSS selector before capturing (30s timeout)')
  .option('--no-animations', 'Disable CSS animations (default: on)', true)
  .action(async (opts) => {
    ensureDir(opts.output);

    await withPage({ viewport: opts.viewport, noAnimations: opts.noAnimations !== false }, async (page) => {
      await navigateSafely(page, opts.url);

      if (opts.waitSelector) {
        await page
          .waitForSelector(opts.waitSelector, { timeout: 30_000 })
          .catch((e: Error) => console.error(`Warning: selector wait timed out: ${e.message}`));
      }

      await page.screenshot({
        path: opts.output,
        fullPage: opts.fullPage as boolean,
      });
    });

    const { size } = fs.statSync(opts.output);
    console.log(`Screenshot saved: ${opts.output} (${(size / 1024).toFixed(0)}KB)`);
  });

// ── record ─────────────────────────────────────────────────────────────────────

program
  .command('record')
  .description('Record a WebM video at a URL')
  .requiredOption('--url <url>', 'URL to record')
  .requiredOption('--output <path>', 'Output WebM path')
  .requiredOption('--duration <seconds>', 'Recording duration in seconds')
  .option('--script <path>', 'JS/TS script executed during recording (exports default fn(page))')
  .option('--viewport <WxH>', 'Viewport dimensions', '1280x800')
  .action(async (opts) => {
    ensureDir(opts.output);
    const duration = parseInt(opts.duration, 10);
    if (isNaN(duration) || duration <= 0) throw new Error(`Invalid duration: ${opts.duration}`);

    const viewport = parseViewport(opts.viewport);
    const videoDir = path.dirname(opts.output);
    let videoPath: string | undefined;

    await withPage(
      {
        viewport: opts.viewport,
        noAnimations: false, // keep animations for recordings
        video: { dir: videoDir, size: viewport },
      },
      async (page) => {
        await navigateSafely(page, opts.url);

        if (opts.script) {
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const mod = require(path.resolve(opts.script));
          const fn = mod.default ?? mod;
          if (typeof fn !== 'function') throw new Error('Recording script must export a default function(page)');
          await fn(page);
        }

        await page.waitForTimeout(duration * 1000);
        videoPath = await page.video()?.path();
      },
    );

    if (!videoPath || !fs.existsSync(videoPath)) {
      console.error('Recording failed: no video file produced');
      process.exit(1);
    }

    fs.renameSync(videoPath, opts.output);

    const { size } = fs.statSync(opts.output);
    const sizeMB = size / (1024 * 1024);
    console.log(`Recording saved: ${opts.output} (${sizeMB.toFixed(1)}MB, ${duration}s)`);

    if (sizeMB > 10) {
      console.error(`Warning: ${sizeMB.toFixed(1)}MB exceeds GitHub's 10MB inline embed limit.`);
      console.error(`Transcode with ffmpeg: ffmpeg -i ${opts.output} -crf 35 -b:v 0 ${opts.output.replace('.webm', '-small.webm')}`);
    }
  });

// ── flow ───────────────────────────────────────────────────────────────────────

program
  .command('flow')
  .description('Execute a scripted multi-step flow, capturing a numbered PNG per step')
  .requiredOption('--script <path>', 'Flow script exporting array of { name, action(page) } steps')
  .requiredOption('--output-dir <dir>', 'Directory for numbered screenshots')
  .option('--url <url>', 'Navigate to this URL before running steps')
  .option('--viewport <WxH>', 'Viewport dimensions', '1280x800')
  .option('--no-animations', 'Disable CSS animations (default: on)', true)
  .action(async (opts) => {
    fs.mkdirSync(opts.outputDir, { recursive: true });

    const steps = await loadFlowScript(opts.script);
    if (steps.length === 0) throw new Error('Flow script has no steps');

    await withPage({ viewport: opts.viewport, noAnimations: opts.noAnimations !== false }, async (page) => {
      if (opts.url) await navigateSafely(page, opts.url);

      for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        if (typeof step.action !== 'function') {
          throw new Error(`Step ${i + 1} ("${step.name}") has no action function`);
        }
        await step.action(page);

        const index = String(i + 1).padStart(2, '0');
        const slug = step.name.replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
        const screenshotPath = path.join(opts.outputDir, `${index}-${slug}.png`);
        await page.screenshot({ path: screenshotPath });
        console.log(`[${i + 1}/${steps.length}] ${step.name} → ${screenshotPath}`);
      }
    });

    console.log(`\nFlow complete: ${steps.length} screenshots in ${opts.outputDir}`);
  });

// ── run ────────────────────────────────────────────────────────────────────────

program.parseAsync(process.argv).catch((e) => {
  console.error(e instanceof Error ? e.message : String(e));
  process.exit(1);
});
