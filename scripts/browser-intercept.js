#!/usr/bin/env node

/**
 * browser-intercept.js
 * =====================
 * Intercept and control network requests for E2E testing.
 *
 * Usage:
 *   browser-intercept.js --path <pattern> --delay 2000
 *   browser-intercept.js --path <pattern> --status 500 --error "msg"
 *   browser-intercept.js --clear
 *
 * Options:
 *   --path <pattern>   URL pattern to intercept (supports wildcards)
 *   --delay <ms>       Delay response by N milliseconds
 *   --status <code>    Return HTTP status code
 *   --error <message>  Return error response with message
 *   --clear            Clear all intercepts
 *   --api <url>        Backend API URL (default: http://localhost:8000)
 *
 * Examples:
 *   # Slow down delete operations to test button disabled state
 *   browser-intercept.js --path "/api/sessions/xyz/messages/abc" --delay 2000
 *
 *   # Simulate server error on chat endpoint
 *   browser-intercept.js --path "/api/chat" --status 500 --error "LLM unavailable"
 *
 *   # Clear all intercepts
 *   browser-intercept.js --clear
 */

import puppeteer from 'puppeteer-core';

const args = process.argv.slice(2);

function getArg(name) {
    const idx = args.indexOf(`--${name}`);
    if (idx === -1) return null;
    return args[idx + 1];
}

const pathPattern = getArg('path');
const delay = parseInt(getArg('delay') || '0', 10);
const status = parseInt(getArg('status') || '0', 10);
const errorMessage = getArg('error');
const clear = args.includes('--clear');
const apiBase = getArg('api') || 'http://localhost:8000';

if (!clear && !pathPattern) {
    console.error(
        'Usage: browser-intercept.js --path <pattern> [--delay ms] [--status code] [--error msg]'
    );
    console.error('       browser-intercept.js --clear');
    process.exit(1);
}

async function run() {
    const b = await Promise.race([
        puppeteer.connect({
            browserURL: 'http://localhost:9222',
            defaultViewport: null
        }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000))
    ]).catch((e) => {
        console.error('✗ Could not connect to browser:', e.message);
        process.exit(1);
    });

    const p = (await b.pages()).at(-1);
    if (!p) {
        console.error('✗ No active tab found');
        await b.disconnect();
        process.exit(1);
    }

    try {
        if (clear) {
            // Clear all intercepts by reloading the page
            await p.evaluate(() => {
                // Remove any stored intercept config
                delete window.__interceptConfig;
            });
            console.log('✓ Cleared all intercepts');
        } else {
            // Configure the intercept
            const config = {
                pathPattern,
                delay,
                status: status || null,
                errorMessage: errorMessage || null,
                apiBase
            };

            await p.evaluate((cfg) => {
                // Store config for the page
                window.__interceptConfig = cfg;

                // Override fetch to intercept matching requests
                const origFetch = window.fetch;
                window.fetch = async function (...args) {
                    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';

                    // Check if URL matches the pattern
                    const regex = new RegExp(
                        cfg.pathPattern.replace(/\*/g, '[^/]*').replace(/\//g, '\\/')
                    );

                    if (regex.test(url)) {
                        // Apply delay if configured
                        if (cfg.delay > 0) {
                            await new Promise((r) => setTimeout(r, cfg.delay));
                        }

                        // Return error if configured
                        if (cfg.status) {
                            return new Response(
                                JSON.stringify({
                                    detail: cfg.errorMessage || 'Test error'
                                }),
                                {
                                    status: cfg.status,
                                    headers: {
                                        'Content-Type': 'application/json'
                                    }
                                }
                            );
                        }
                    }

                    // Pass through to original fetch
                    return origFetch.apply(this, args);
                };
            }, config);

            let desc = `Pattern: ${pathPattern}`;
            if (delay > 0) desc += `, Delay: ${delay}ms`;
            if (status) desc += `, Status: ${status}`;
            if (errorMessage) desc += `, Error: "${errorMessage}"`;
            console.log(`✓ Intercept configured: ${desc}`);
        }
    } finally {
        await b.disconnect();
    }
}

run().catch((e) => {
    console.error('✗ Error:', e.message);
    process.exit(1);
});
