import './app-core.js';

function applyWorkspacePolish(){
  const sidebar=document.querySelector('#sidebar');
  const close=document.querySelector('#sidebar-close');
  if(document.querySelector('.sidebar-note')) document.querySelector('.sidebar-note').remove();
  if(close && !close.dataset.responsiveBound){
    const replacement=close.cloneNode(true);
    replacement.setAttribute('aria-label','Collapse navigation');
    replacement.setAttribute('title','Collapse navigation');
    replacement.dataset.responsiveBound='true';
    close.replaceWith(replacement);
    replacement.addEventListener('click',(event)=>{event.preventDefault();event.stopPropagation();setSidebar(false);});
  }
  document.querySelector('#back-button')?.remove();
  document.querySelector('#connection')?.remove();
  document.querySelector('.setup-card')?.remove();
  const subtitle=document.querySelector('#greeting')?.nextElementSibling;if(subtitle) subtitle.remove();
  const history=document.querySelector('#stat-history')?.closest('.stat-card');if(history) history.remove();
  const inbox=document.querySelector('#stat-inbox')?.closest('.stat-card');if(inbox) inbox.remove();
  const preferred=document.querySelector('#top-profile-name')?.textContent?.trim()||'there';
  const greeting=document.querySelector('#greeting');
  if(greeting){const isNew=sessionStorage.getItem('known.new-user')==='true';greeting.textContent=`${isNew?'Welcome':'Welcome back'}, ${preferred}`;}
}
function setSidebar(open){const sidebar=document.querySelector('#sidebar');const backdrop=document.querySelector('#sidebar-backdrop');if(!sidebar)return;sidebar.classList.toggle('collapsed',!open);const mobile=window.matchMedia('(max-width: 900px)').matches;if(backdrop)backdrop.hidden=!(mobile&&open);document.body.classList.toggle('sidebar-open',mobile&&open);}
function bindResponsiveDrawer(){const sidebar=document.querySelector('#sidebar'),hamburger=document.querySelector('#hamburger'),backdrop=document.querySelector('#sidebar-backdrop');if(!sidebar)return;hamburger?.addEventListener('click',()=>setSidebar(true));backdrop?.addEventListener('click',()=>setSidebar(false));window.addEventListener('resize',()=>{const mobile=window.matchMedia('(max-width: 900px)').matches;if(!mobile&&backdrop)backdrop.hidden=true;},{passive:true});}
if(!document.querySelector('link[data-workspace-responsive]')){const link=document.createElement('link');link.rel='stylesheet';link.href='./workspace-responsive.css?v=2';link.dataset.workspaceResponsive='true';document.head.appendChild(link);}
setTimeout(()=>{applyWorkspacePolish();bindResponsiveDrawer();setSidebar(true);},250);setTimeout(()=>applyWorkspacePolish(),900);
