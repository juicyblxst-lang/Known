import './app-core.js';

function applyWorkspacePolish(){
  const sidebar=document.querySelector('#sidebar');
  const close=document.querySelector('#sidebar-close');
  if(document.querySelector('.sidebar-note')) document.querySelector('.sidebar-note').remove();

  // Replace the desktop collapse control so it never logs the user out.
  if(close && !close.dataset.responsiveBound){
    const replacement=close.cloneNode(true);
    replacement.setAttribute('aria-label','Collapse navigation');
    replacement.dataset.responsiveBound='true';
    close.replaceWith(replacement);
    replacement.addEventListener('click',()=>setSidebar(false));
  }

  // Keep the hamburger available to the responsive layer. CSS hides it on desktop.
  document.querySelector('#back-button')?.remove();
  document.querySelector('#connection')?.remove();
  document.querySelector('.setup-card')?.remove();
  const subtitle=document.querySelector('#greeting')?.nextElementSibling;
  if(subtitle) subtitle.remove();
  const history=document.querySelector('#stat-history')?.closest('.stat-card');
  if(history) history.remove();
  const inbox=document.querySelector('#stat-inbox')?.closest('.stat-card');
  if(inbox) inbox.remove();

  const preferred=document.querySelector('#top-profile-name')?.textContent?.trim()||'there';
  const greeting=document.querySelector('#greeting');
  if(greeting){
    const isNew=sessionStorage.getItem('known.new-user')==='true';
    greeting.textContent=`${isNew?'Welcome onboard':'Welcome back'}, ${preferred}`;
    sessionStorage.removeItem('known.new-user');
  }
}

function setSidebar(open){
  const sidebar=document.querySelector('#sidebar');
  const backdrop=document.querySelector('#sidebar-backdrop');
  if(!sidebar)return;
  sidebar.classList.toggle('collapsed',!open);
  const mobile=window.matchMedia('(max-width: 900px)').matches;
  if(backdrop) backdrop.hidden=!(mobile && open);
  document.body.classList.toggle('sidebar-open',mobile && open);
}

function bindResponsiveDrawer(){
  const sidebar=document.querySelector('#sidebar');
  const hamburger=document.querySelector('#hamburger');
  const backdrop=document.querySelector('#sidebar-backdrop');
  if(!sidebar)return;

  hamburger?.addEventListener('click',()=>setSidebar(true));
  backdrop?.addEventListener('click',()=>setSidebar(false));

  // Any navigation item can open the drawer on mobile; tapping outside remains
  // the explicit way to dismiss it without changing the current view.
  document.querySelectorAll('.nav-item').forEach(item=>{
    item.addEventListener('click',()=>{
      if(window.matchMedia('(max-width: 900px)').matches) setSidebar(true);
    });
  });

  const sync=()=>{
    const mobile=window.matchMedia('(max-width: 900px)').matches;
    if(!mobile && backdrop) backdrop.hidden=true;
    if(mobile && backdrop) backdrop.hidden=sidebar.classList.contains('collapsed');
    document.body.classList.toggle('sidebar-open',mobile && !sidebar.classList.contains('collapsed'));
  };
  window.addEventListener('resize',sync,{passive:true});
  sync();
}

if(!document.querySelector('link[data-workspace-responsive]')){
  const link=document.createElement('link');
  link.rel='stylesheet';
  link.href='./workspace-responsive.css?v=2';
  link.dataset.workspaceResponsive='true';
  document.head.appendChild(link);
}

setTimeout(()=>{
  applyWorkspacePolish();
  bindResponsiveDrawer();
  setSidebar(true);
},250);
setTimeout(()=>applyWorkspacePolish(),900);
