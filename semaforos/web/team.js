'use strict';

window.teamSession = {
  async open(key) {
    const response = await fetch('/report-media/session', {
      method:'POST', headers:{Authorization:'Bearer '+key}, cache:'no-store'
    });
    if (!response.ok) throw Error('No se pudo entrar. Comprueba la clave del equipo.');
  },
  async active() {
    try {
      const response=await fetch('/team-session',{cache:'no-store'});
      return response.ok;
    } catch { return false; }
  },
  async close() {
    const response=await fetch('/report-media/session',{method:'DELETE',cache:'no-store'});
    if (!response.ok) throw Error('No se pudo cerrar la sesión del equipo.');
  }
};

if (location.pathname !== '/semaforos') {
  const title=document.querySelector('h1');
  const section=document.createElement('div');
  section.className='team-brand';
  const name=document.createElement('h1');
  name.textContent='Acción Popular - Cali Semáforos Dañados';
  const subtitle=document.createElement('p');
  subtitle.textContent='Procesamiento y presentación de evidencias enviadas por ciudadanos a través de WhatsApp';
  const picture=document.createElement('img');
  picture.src='/marca-esteban.png';
  picture.alt='Ingeniero Esteban Oli';
  picture.width=190;
  picture.height=47;
  const brand=document.createElement('div');
  brand.append(name,picture);
  const navigation=document.createElement('nav');
  navigation.setAttribute('aria-label','Panel del equipo');
  const detail=location.pathname==='/reportes' &&
    (new URLSearchParams(location.search).has('registro') || new URLSearchParams(location.search).has('detalle'));
  for (const [label,href,active] of [
    ['Reporte','/reportes',location.pathname==='/reportes' && !detail],
    ['Desempeño de modelos','/metricas',location.pathname==='/metricas'],
    ['Detalle de reporte','/reportes?detalle=1',detail],
    ['Cargue de ZIP','/',location.pathname==='/']
  ]) {
    const link=document.createElement('a');
    link.href=href;
    link.textContent=label;
    if (active) link.setAttribute('aria-current','page');
    navigation.append(link);
  }
  section.append(brand,subtitle,navigation);
  title.closest('main').prepend(section);
  if (location.pathname==='/reportes') {
    document.querySelector('.report-intro').hidden=true;
  } else {
    const heading=document.createElement('h2');
    heading.textContent=location.pathname==='/'?'Cargue de ZIP':title.textContent;
    title.replaceWith(heading);
  }
}
