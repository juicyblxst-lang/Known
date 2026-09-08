import { getSession, onboardingStatus, completeOnboarding } from './auth.js';

let session = null;
let state = null;
let overlay = null;
let card = null;
let spotlight = null;
let currentStep = null;
let refreshTimer = null;

const $ = (selector) => document.querySelector(selector);

function hasCustomers() {
  const value = Number(String($('#stat-customers')?.textContent || '0').replace(/,/g, ''));
  return value > 0;
}

function build() {
  if ($('#known-first-run-tour')) return;
  overlay = document.createElement('div');
  overlay.id = 'known-first-run-tour';
  overlay.className = 'known-tour-overlay';
  overlay.innerHTML = `
    <div class="known-tour-backdrop"></div>
    <div class="known-tour-spotlight" aria-hidden="true"></div>
    <section class="known-tour-card" role="dialog" aria-modal="true" aria-labelledby="known-tour-title">
      <div class="known-tour-progress"><span id="known-tour-step">SETUP · 1/4</span><span>FIRST WORKSPACE</span></div>
      <h2 id="known-tour-title"></h2>
      <p id="known-tour-copy"></p>
      <div id="known-tour-detail" class="known-tour-detail"></div>
      <div class="known-tour-actions"><button id="known-tour-action" type="button"></button></div>
    </section>`;
  document.body.appendChild(overlay);
  card = $('.known-tour-card');
  spotlight = $('.known-tour-spotlight');
  $('#known-tour-action').addEventListener('click', handleAction);
}

function hide() {
  if (overlay) overlay.hidden = true;
  document.querySelectorAll('.known-tour-target').forEach((el) => el.classList.remove('known-tour-target'));
}

function show() { if (overlay) overlay.hidden = false; }

function targetFor(step) {
  if (step === 'setup') return document.querySelector('[data-view="settings"]');
  if (step === 'csv-file') return $('#csv-file');
  if (step === 'csv-import') return $('#import-csv');
  if (step === 'gmail') return $('#connect-gmail');
  return null;
}

function position(step) {
  const target = targetFor(step);
  document.querySelectorAll('.known-tour-target').forEach((el) => el.classList.remove('known-tour-target'));
  if (!target) {
    spotlight.style.display = 'none';
    card.classList.remove('anchored');
    card.style.left = '';
    card.style.top = '';
    return;
  }
  target.classList.add('known-tour-target');
  const rect = target.getBoundingClientRect();
  spotlight.style.display = 'block';
  spotlight.style.left = `${Math.max(8, rect.left - 8)}px`;
  spotlight.style.top = `${Math.max(8, rect.top - 8)}px`;
  spotlight.style.width = `${rect.width + 16}px`;
  spotlight.style.height = `${rect.height + 16}px`;
  card.classList.add('anchored');
  const width = Math.min(380, window.innerWidth - 32);
  let left = rect.left;
  let top = rect.bottom + 18;
  if (left + width > window.innerWidth - 16) left = window.innerWidth - width - 16;
  if (top + 260 > window.innerHeight - 16) top = Math.max(16, rect.top - 278);
  card.style.width = `${width}px`;
  card.style.left = `${Math.max(16, left)}px`;
  card.style.top = `${top}px`;
}

function setStep(step) {
  currentStep = step;
  show();
  const copy = {
    welcome: ['SETUP · 1/4', 'Let’s get Known ready.', 'You only need to do two things. First, bring in your existing customer history. Then connect the Gmail inbox your customers already use. Known handles the memory and support workflow behind the scenes.', 'Start with your customer history.', 'Begin setup'],
    setup: ['SETUP · 2/4', 'Bring your customer history into Known.', 'Open Setup and choose the CSV your business already uses. This gives Known the customer foundation it needs before support conversations arrive.', 'No technical configuration is required.', 'Open setup'],
    'csv-file': ['SETUP · 3/4', 'Choose your customer history CSV.', 'Select the CSV export containing your customers or orders. Known will inspect it before importing anything.', 'After inspection, the Add to Customers button will become available.', 'Choose CSV'],
    'csv-import': ['SETUP · 3/4', 'Review the import, then add it.', 'Known has inspected the file. Add it to Customers to save the customer and order history to your workspace.', 'You can continue immediately after the import finishes.', 'Add to Customers'],
    gmail: ['SETUP · 4/4', 'Connect the Gmail inbox your customers use.', 'This is the last setup step. Connect your support Gmail so Known can receive conversations, match them to customers, retrieve context, and keep the memory current.', 'Google handles the secure connection. You do not need to configure Gmail manually.', 'Connect Gmail']
  }[step];
  if (!copy) return;
  $('#known-tour-step').textContent = copy[0];
  $('#known-tour-title').textContent = copy[1];
  $('#known-tour-copy').textContent = copy[2];
  $('#known-tour-detail').textContent = copy[3];
  const action = $('#known-tour-action');
  action.textContent = copy[4];
  action.disabled = false;
  position(step);
}

async function finish() {
  try {
    await completeOnboarding(session);
  } catch (error) {
    console.warn('Known first-run completion could not be persisted:', error);
    return;
  }
  state = { completed: true };
  if (refreshTimer) clearInterval(refreshTimer);
  currentStep = 'done';
  spotlight.style.display = 'none';
  document.querySelectorAll('.known-tour-target').forEach((el) => el.classList.remove('known-tour-target'));
  card.classList.remove('anchored');
  card.style.left = '';
  card.style.top = '';
  $('#known-tour-step').textContent = 'SETUP COMPLETE';
  $('#known-tour-title').textContent = 'You’re ready to support customers.';
  $('#known-tour-copy').textContent = 'Known is now connected to your customer history and support inbox. New conversations can be matched with customer context automatically.';
  $('#known-tour-detail').textContent = 'You can now explore Customers, Inbox, and the customer workspace from the dashboard.';
  const action = $('#known-tour-action');
  action.textContent = 'Enter workspace';
  action.onclick = hide;
}

async function handleAction() {
  const action = $('#known-tour-action');
  if (currentStep === 'welcome') {
    if (hasCustomers()) {
      document.querySelector('[data-view="settings"]')?.click();
      return setTimeout(() => setStep('gmail'), 180);
    }
    return setStep('setup');
  }
  if (currentStep === 'setup') {
    document.querySelector('[data-view="settings"]')?.click();
    return setTimeout(() => setStep(hasCustomers() ? 'gmail' : 'csv-file'), 180);
  }
  if (currentStep === 'csv-file') return $('#csv-file')?.click();
  if (currentStep === 'csv-import') {
    action.disabled = true;
    return $('#import-csv')?.click();
  }
  if (currentStep === 'gmail') return $('#connect-gmail')?.click();
  if (currentStep === 'done') return hide();
}

async function refreshGmailState() {
  try {
    const response = await fetch('/api/integrations/gmail/status', { headers: { Authorization: `Bearer ${session.accessToken}` } });
    if (!response.ok) return;
    const data = await response.json();
    if (data.connected && !state.completed) await finish();
  } catch { /* dashboard integration owns the normal status handling */ }
}

function inspectProgress() {
  if (!currentStep) return;
  if (currentStep === 'csv-file' && $('#csv-file')?.files?.length) setStep('csv-import');
  if (currentStep === 'csv-import' && hasCustomers()) setStep('gmail');
}

async function start() {
  if (location.pathname.endsWith('/onboarding.html')) return;
  try {
    session = await getSession();
    if (!session) return;
    state = await onboardingStatus(session);
    if (state.completed) return;
    build();
    setStep('welcome');
    window.addEventListener('resize', () => position(currentStep));
    window.addEventListener('scroll', () => position(currentStep), true);
    window.addEventListener('known:import-complete', () => setStep('gmail'));
    window.addEventListener('known:gmail-status', async (event) => {
      if (event.detail?.connected && !state.completed) await finish();
    });
    refreshTimer = setInterval(inspectProgress, 600);
    await refreshGmailState();
  } catch (error) {
    console.warn('Known first-run guide unavailable:', error);
  }
}

start();
