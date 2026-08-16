# Despliegue — diseño

## Objetivo

Sacar el proyecto de "solo corre en mi máquina" a algo que corre solo:
`recolectar.py` en un horario fijo, sin que nadie tenga que acordarse de
ejecutarlo, y la app accesible por un link en vez de `streamlit run`
local. Mencionado como plan siguiente en la sección "Al terminar" de
[`2026-08-03-app-streamlit.md`](../plans/2026-08-03-app-streamlit.md) y en
el spec principal.

## Decisiones

### 1. Repositorio en GitHub

El proyecto no tenía remoto — es la primera vez que sale de esta
máquina. Repo **privado**, creado nuevo. GitHub Actions y Streamlit Cloud
se conectan a este mismo repo; no hace falta que sea público para que
Streamlit Cloud lo despliegue.

`mapa-mercado-laboral` es un proyecto completamente aparte, en otro
directorio, sin remoto compartido ni referencia cruzada — este plan no lo
toca de ninguna forma.

### 2. Base de datos: Supabase (Postgres) nuevo, arranque limpio

Ya existe un proyecto de Supabase creado para este despliegue (no
compartido con nada más), con `.streamlit/secrets.toml` local ya
apuntando ahí y `conexion.diagnostico()` confirmando que la conexión
funciona. **Arranca vacío — no se migra `data/buscador.db`** (decisión
explícita: las 3.446 ofertas que ya se juntaron localmente se quedan como
están, sirviendo para desarrollo local; la nube junta las suyas desde
cero).

`db.py` ya sabe operar contra Postgres o SQLite según qué devuelva
`conexion.url_postgres()` (`db.engine()` sin `db_path` explícito) — no
hace falta ningún cambio de código para que `recolectar.py`, `seed.py` y
`app.py` funcionen igual contra la nube.

### 3. GitHub Actions: recolección programada

Un workflow (`.github/workflows/recolectar.yml`) que:

- Corre en un cron diario, de madrugada hora Chile (~6am UTC).
- También se puede disparar a mano (`workflow_dispatch`) — útil para
  probar el despliegue sin esperar un día.
- Instala `requirements.txt` (ya tiene todo lo necesario: `requests`,
  `sqlalchemy`, `psycopg[binary]` — nada de scraping HTML depende de una
  librería aparte, todo el parseo usa `re` de la librería estándar).
- Corre `seed.py` primero, después `recolectar.py`. `seed.run` es
  idempotente (no repisa términos que ya existen) — con esto delante,
  una base de Supabase recién creada se autopuebla con los 26 términos
  base en la primera corrida, sin un paso manual aparte. Con el tiempo,
  cuando la base ya tenga los 26 términos, este paso es casi gratis (una
  sola consulta `SELECT termino FROM terminos_busqueda`).
- Pasa la conexión a Supabase como **GitHub Secrets** (`POSTGRES_URL`,
  `POSTGRES_PASSWORD`), inyectados como variables de entorno del job —
  `conexion.leer()` ya las lee primero, antes que `secrets.toml` local,
  así que no hace falta ningún cambio de código, solo configurar los
  secrets en GitHub.

**Presupuesto de tiempo:** `recolectar.py` ya trae
`PRESUPUESTO_SEGUNDOS_DEFECTO = 45 * 60` (heredado del spec de
Recolección). Una corrida diaria de 45 minutos son ~1.350 minutos/mes —
dentro de los 2.000 minutos/mes gratis que da GitHub Actions para repos
privados, con margen para correr el workflow a mano alguna vez de más sin
quedarse sin cupo. No se toca este número en este plan; si el consumo real
resulta muy distinto, se ajusta con datos, no a ojo (mismo criterio que
ya costó una vez en el plan de Búsqueda en vivo).

### 4. Streamlit Cloud: la app

Se conecta el repo (ya existe cuenta en share.streamlit.io — el usuario
autoriza el acceso a GitHub, es un paso manual de su lado, no algo que se
automatice). Configuración:

- Archivo principal: `app.py`.
- Secrets: se pegan en el panel de Streamlit Cloud, mismo formato TOML
  que ya usa `secrets.toml` local (`[conexion]` con `postgres_url` y
  `password`). Streamlit Cloud escribe esto a un `.streamlit/secrets.toml`
  real dentro del contenedor de la app — mismo mecanismo de lectura que
  `conexion.py` ya usa (`tomllib` sobre un archivo físico, no `st.secrets`
  en código). Este punto se verifica de forma empírica en el momento del
  despliegue: si Streamlit Cloud lo expone distinto de lo esperado,
  ajustar `conexion.leer()` para también intentar `st.secrets` como
  alternativa — no se puede confirmar sin desplegar de verdad.

### 5. Login: sin cambios por ahora

Sigue siendo solo por correo, sin contraseña — decisión explícita: el
primer despliegue es para el usuario y un círculo cercano de confianza,
no un lanzamiento público. El link de Streamlit Cloud no se comparte
públicamente ni se promociona ("no listado", no protegido de verdad,
pero suficiente para esta audiencia). `st.login()` con OIDC y la revisión
del marco legal chileno de datos personales (Ley 19.628 / 21.719, ya
señalada como pendiente en el spec principal) quedan explícitamente fuera
de este plan — se retoman en un plan aparte si la app se abre a
desconocidos.

## Fuera de alcance

- Login real (`st.login()` OIDC) — condicionado a tener audiencia
  pública real, como ya decía el spec principal.
- Migrar los datos locales a Supabase.
- Dominio propio / URL personalizada para la app.
- Monitoreo o alertas si el workflow de GitHub Actions falla (por ahora,
  GitHub ya notifica por correo al dueño del repo si un workflow
  programado falla — es el comportamiento por defecto, no algo que este
  plan tenga que construir).
