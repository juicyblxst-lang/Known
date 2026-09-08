import { getSession, onboardingStatus, completeOnboarding } from './auth.js';

let session = null;
let state = null;
let overlay = null;
let card = null;
let spotlight = null;
let currentStep = null;
let refreshTimer = null;
let finishing = false;

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
  if (step === 'gmail') return $('#connect-gmail');
  if (step === 'csv-file') return $('#csv-file');
  if (step === 'csv-import') return $('#import-csv');
  return null;
}

function position(step) {
  const target = targetFor(step);
  document.querySelectorAll('.known-tour-target').forEach((el) => el.classList.remove('known-tour-target'));
  if (!target || target.offsetParent === null) {
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
  const estimatedHeight = Math.min(330, window.innerHeight - 32);
  if (left + width > window.innerWidth - 16) left = window.innerWidth - width - 16;
  if (top + estimatedHeight > window.innerHeight - 16) top = Math.max(16, rect.top - estimatedHeight - 18);
  card.style.width = `${width}px`;
  card.style.left = `${Math.max(16, left)}px`;
  card.style.top = `${Math.max(16, top)}px`;
}

function setStep(step) {
  currentStep = step;
  show();
  const copy = {
    welcome: ['SETUP · 1/4', 'Let’s get Known ready.', 'There are two setup actions: connect the support Gmail first, then import your customer history. Known handles the memory and support workflow behind the scenes.', 'You can use the workspace normally once setup is complete.', 'Begin setup'],
    setup: ['SETUP · 2/4', 'Open setup.', 'We’ll connect the support inbox first. After Gmail is connected, Known will guide you through importing your customer history.', 'No technical configuration is required.', 'Open setup'],
    gmail: ['SETUP · 3/4', 'Connect the Gmail inbox your customers use.', 'This comes before importing customer history. Connect your support Gmail so Known can receive conversations, match them to customers, retrieve context, and keep memory current.', 'Google handles the secure connection. You do not need to configure Gmail manually.', 'Connect Gmail'],
    'csv-file': ['SETUP · 4/4', 'Now import your customer history.', 'Choose the CSV export containing your customers or orders. Known will inspect it before importing anything.', 'After inspection, the Add to Customers button will become available.', 'Choose CSV'],
    'csv-import': ['SETUP · 4/4', 'Review the import, then add it.', 'Known has inspected the file. Add it to Customers to save the customer and order history to your workspace.', 'After the import finishes, setup is complete.', 'Add to Customers']
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
  if (finishing || state?.completed) return;
  finishing = true;
  try {
    await completeOnboarding(session);
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
    $('#known-tour-copy').textContent = 'Known is now connected to your support inbox and customer history. New conversations can be matched with customer context automatically.';
    $('#known-tour-detail').textContent = 'You can now explore Customers, Inbox, and the customer workspace from the dashboard.';
    const action = $('#known-tour-action');
    action.textContent = 'Enter workspace';
    action.disabled = false;
  } catch (error) {
    console.warn('Known first-run completion could not be persisted:', error);
  } finally {
    finishing = false;
  }
}

async function handleAction() {
  const action = $('#known-tour-action');
  if (currentStep === 'welcome') return setStep('setup');
  if (currentStep === 'setup') {
    document.querySelector('[data-view="settings"]')?.click();
    return setTimeout(() => setStep('gmail'), 180);
  }
  if (currentStep === 'gmail') return $('#connect-gmail')?.click();
  if (currentStep === 'csv-file') return $('#csv-file')?.click();
  if (currentStep === 'csv-import') {
    action.disabled = true;
    return $('#import-csv')?.click();
  }
  if (currentStep === 'done') return hide();
}

async function refreshGmailState() {
  try {
    const response = await fetch('/api/integrations/gmail/status', { headers: { Authorization: `Bearer ${session.accessToken}` } });
    if (!response.ok) return;
    const data = await response.json();
    if (data.connected && !state.completed) {
      if (hasCustomers()) await finish();
      else setStep('csv-file');
    }
  } catch { /* dashboard integration owns normal status handling */ }
}

function inspectProgress() {
  if (!currentStep || state?.completed) return;
  if (currentStep === 'csv-file' && $('#csv-file')?.files?.length) setStep('csv-import');
  if (currentStep === 'csv-import' && hasCustomers() && !finishing) finish();
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
    window.addEventListener('known:import-complete', async () => {
      if (!state.completed) await finish();
    });
    window.addEventListener('known:gmail-status', async (event) => {
      if (event.detail?.connected && !state.completed) {
        if (hasCustomers()) await finish();
        else setStep('csv-file');
      }
    });
    refreshTimer = setInterval(inspectProgress, 600);
    await refreshGmailState();
  } catch (error) {
    console.warn('Known first-run guide unavailable:', error);
  }
}

start();
