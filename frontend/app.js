import './app-core.js';

function applyWorkspacePolish(){
  const sidebar=document.querySelector('#sidebar');
  const close=document.querySelector('#sidebar-close');
  if(document.querySelector('.sidebar-note')) document.querySelector('.sidebar-note').remove();
  if(close){
    const replacement=close.cloneNode(true);
    replacement.setAttribute('aria-label','Collapse navigation');
    close.replaceWith(replacement);
    replacement.addEventListener('click',()=>sidebar?.classList.toggle('collapsed'));
  }
  document.querySelector('#hamburger')?.remove();
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
setTimeout(applyWorkspacePolish,250);
setTimeout(applyWorkspacePolish,900);
