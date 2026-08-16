# Despliegue — plan de implementación

> **For agentic workers:** este plan mezcla código puro (Tarea 1, delegable
> a un subagente) con acciones de infraestructura reales — crear un repo,
> hacer push, configurar secrets, disparar un workflow — que la política
> de seguridad del entorno exige confirmar explícitamente con la persona
> antes de ejecutar, y que por su naturaleza no son delegables a un
> subagente aislado (necesitan la sesión con acceso ya autenticado a
> `gh`, y en el caso de Streamlit Cloud, un paso que solo la persona puede
> hacer — autorizar OAuth). Las Tareas 2-5 se ejecutan en la sesión
> principal, no vía `superpowers:subagent-driven-development`, con
> confirmación antes de cada acción irreversible o visible externamente
> (push, creación de secrets, disparo del workflow). Ver la nota al final
> de cada tarea 2-5 en vez de un paso de "Commit" tipo TDD.

**Goal:** Sacar el proyecto de "solo corre en mi máquina" — `recolectar.py`
en un horario fijo vía GitHub Actions, la app accesible por un link vía
Streamlit Cloud, ambos contra el Supabase ya creado y verificado.

**Architecture:** Repo privado nuevo en GitHub (el proyecto nunca tuvo
remoto). Un workflow de GitHub Actions corre `seed.py` + `recolectar.py`
en cron diario contra Supabase, usando las mismas variables de entorno
que `conexion.py` ya sabe leer — cero cambios de código para la
recolección programada. Streamlit Cloud despliega `app.py` desde el mismo
repo, con los secrets pegados en su panel en el mismo formato TOML que
`secrets.toml` local.

**Tech Stack:** GitHub Actions (YAML), `gh` CLI (ya autenticado en esta
sesión, scopes `repo`+`workflow`), Streamlit Cloud (share.streamlit.io).
Nada nuevo en Python — `requirements.txt` ya tiene todo lo necesario.

## Global Constraints

- **Repo privado**, nuevo, sin migrar `data/buscador.db` — Supabase
  arranca vacío (decisión explícita del usuario).
- **`mapa-mercado-laboral` no se toca de ninguna forma** — proyecto
  aparte, sin remoto compartido, verificado en esta sesión.
- **Cron diario de madrugada (~6am UTC)** + disparo manual
  (`workflow_dispatch`) — no más seguido: el umbral de 24h que ya usa
  `db.terminos_pendientes` hace que correr más seguido no traiga nada
  nuevo.
- **`seed.py` corre antes que `recolectar.py`** en cada corrida del
  workflow — idempotente, así una base nueva se autopuebla con los 26
  términos base sin un paso manual aparte.
- **Credenciales de Supabase van como GitHub Secrets**
  (`POSTGRES_URL`, `POSTGRES_PASSWORD`), inyectadas como variables de
  entorno — `conexion.leer()` ya las lee primero, antes que
  `secrets.toml` local. Cero cambios de código.
- **Login sigue siendo solo por correo** — fuera de alcance de este plan
  cambiar a `st.login()`/OIDC (el spec principal lo condiciona a tener
  audiencia pública real). El link de Streamlit Cloud no se comparte
  públicamente.
- **Ninguna acción que empuje código, cree secrets o dispare un workflow
  se ejecuta sin confirmación explícita en el chat primero** — ver nota
  del encabezado.
- Spec de referencia:
  [`docs/superpowers/specs/2026-08-16-despliegue-design.md`](../specs/2026-08-16-despliegue-design.md).

---

## Estructura de archivos

```
buscador-empleo-personalizado/
└── .github/
    └── workflows/
        └── recolectar.yml    nuevo — cron diario + disparo manual
```

Nada más se crea o modifica. `conexion.py`, `db.py`, `recolectar.py`,
`seed.py` ya están listos para correr contra Postgres vía variables de
entorno — es exactamente lo que este plan usa, sin tocarlos.

---

### Task 1: Workflow de GitHub Actions

Escribe el archivo del workflow y verifica, en esta misma máquina, que el
mecanismo del que depende (conexión a Postgres solo por variables de
entorno, sin `secrets.toml`) funciona de verdad — antes de que dependa de
una corrida real en GitHub para descubrir un problema de conexión.

**Files:**
- Create: `.github/workflows/recolectar.yml`

**Interfaces:**
- Consumes: `conexion.leer()` (ya existente — lee `POSTGRES_URL`/
  `POSTGRES_PASSWORD` de variables de entorno antes que de
  `secrets.toml`), `db.engine()`, `seed.py`/`recolectar.py` (ya
  existentes, sin cambios)

- [ ] **Step 1: Crear el workflow**

Crear `.github/workflows/recolectar.yml`:

```yaml
name: Recolección diaria

on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  recolectar:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Instalar dependencias
        run: pip install -r requirements.txt

      - name: Sembrar términos base (idempotente)
        run: python seed.py
        env:
          POSTGRES_URL: ${{ secrets.POSTGRES_URL }}
          POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}

      - name: Recolectar ofertas
        run: python recolectar.py
        env:
          POSTGRES_URL: ${{ secrets.POSTGRES_URL }}
          POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
```

`timeout-minutes: 60` da margen sobre los 45 minutos de
`PRESUPUESTO_SEGUNDOS_DEFECTO` de `recolectar.py` más el tiempo de
instalar dependencias — si algo se cuelga, el job se corta solo en vez de
consumir minutos de más.

- [ ] **Step 2: Verificar el mecanismo de conexión por variables de
  entorno, localmente**

Esto es lo único que se puede probar sin GitHub todavía: que
`POSTGRES_URL`/`POSTGRES_PASSWORD` como variables de entorno (no
`secrets.toml`) alcanzan para que `conexion.py`/`db.py` se conecten a
Postgres — exactamente el mecanismo que el workflow usa.

Necesitás la cadena de conexión y la contraseña que ya usaste para
`secrets.toml` (Sección "Global Constraints" del spec — ya verificado
que funciona). En PowerShell, en la raíz del proyecto:

```powershell
$env:POSTGRES_URL = "postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx-1.pooler.supabase.com:5432/postgres"
$env:POSTGRES_PASSWORD = "tu-contraseña-real"
.venv\Scripts\python.exe -c "import conexion; print(conexion.diagnostico() or 'OK, todo listo')"
Remove-Item Env:\POSTGRES_URL
Remove-Item Env:\POSTGRES_PASSWORD
```

Esperado: `OK, todo listo` — si sale un mensaje de diagnóstico en vez de
eso, revisar la cadena/contraseña antes de seguir (no tiene sentido
avanzar a la Tarea 2 sin esto confirmado).

- [ ] **Step 3: Validar la sintaxis del YAML**

```powershell
.venv\Scripts\python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/recolectar.yml', encoding='utf-8')); print('YAML valido')"
```

Si `pyyaml` no está instalado (`requirements-dev.txt` no lo incluye, no
hace falta agregarlo — es un chequeo de una sola vez): usar cualquier
validador de YAML online, o simplemente confiar en la sintaxis de arriba
(GitHub también valida al primer push; este paso es solo para no
descubrir un error de indentación recién en la Tarea 4).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/recolectar.yml
git commit -m "feat: workflow de GitHub Actions para recoleccion diaria"
```

Este commit SÍ se hace en la rama local, igual que cualquier otro — lo
que se pospone para pedir confirmación explícita es el *push* (Tarea 2),
no el commit local.

---

### Task 2: Crear el repo en GitHub y hacer el primer push

**No delegable a un subagente aislado** — usa el `gh` ya autenticado de
esta sesión, y el push es una acción visible externamente que requiere
confirmación explícita antes de ejecutarse (política del entorno).

- [ ] **Step 1: Confirmar con la persona antes de crear el repo**

Preguntar en el chat: nombre del repo (sugerido: `buscador-empleo-personalizado`,
mismo nombre que la carpeta local), y confirmar que sigue siendo
**privado**. Esperar una respuesta explícita antes de seguir.

- [ ] **Step 2: Crear el repo (sin push todavía)**

```bash
gh repo create buscador-empleo-personalizado --private --description "Buscador de empleo personalizado — Chile" --disable-wiki
```

Esto crea el repo vacío en GitHub, no toca el remoto local todavía.

- [ ] **Step 3: Confirmar con la persona antes del push**

Mostrar `git log --oneline -5` y `git status` para que la persona vea
exactamente qué va a subirse, y preguntar explícitamente si se confirma
el push. Esperar un sí explícito.

- [ ] **Step 4: Conectar el remoto y hacer push**

```bash
git remote add origin https://github.com/paatooo/buscador-empleo-personalizado.git
git push -u origin main
```

- [ ] **Step 5: Verificar**

```bash
gh repo view --web
```

Confirmar a simple vista que el código subió completo (archivos, no solo
el README) y que el repo efectivamente aparece como privado.

---

### Task 3: Configurar los secrets de GitHub

**No delegable a un subagente aislado** — maneja la contraseña real de
la base de datos. Se hace en la sesión principal, con la persona
presente, sin que la contraseña pase nunca por el texto del chat.

- [ ] **Step 1: Confirmar con la persona antes de crear los secrets**

Preguntar explícitamente: "¿confirmás que configure `POSTGRES_URL` y
`POSTGRES_PASSWORD` como secrets del repo en GitHub, usando los mismos
valores que ya están en tu `secrets.toml` local?" Esperar un sí.

- [ ] **Step 2: Configurar los secrets sin que pasen por el chat**

`gh secret set` lee el valor desde un archivo o desde stdin — nunca hace
falta escribir la contraseña en un mensaje. Dos opciones, cualquiera
sirve:

```bash
# Opción A: pegando el valor a mano cuando el comando lo pida (queda en
# la terminal de la persona, no en el historial de chat)
gh secret set POSTGRES_URL
gh secret set POSTGRES_PASSWORD

# Opción B: leyendo directo del secrets.toml local con una herramienta
# que ya sabe parsear ese archivo (evita que la persona tenga que copiar
# y pegar a mano)
.venv\Scripts\python.exe -c "import conexion; d = conexion.leer(); print(d['postgres_url'])" | gh secret set POSTGRES_URL
.venv\Scripts\python.exe -c "import conexion; d = conexion.leer(); print(d['password'])" | gh secret set POSTGRES_PASSWORD
```

- [ ] **Step 3: Verificar (sin exponer los valores)**

```bash
gh secret list
```

Esperado: `POSTGRES_URL` y `POSTGRES_PASSWORD` aparecen en la lista, con
fecha de actualización de hoy. `gh secret list` nunca muestra el valor,
solo el nombre — no hay riesgo de exposición en este chequeo.

---

### Task 4: Disparar el workflow a mano y confirmar que corre bien

**No delegable a un subagente aislado** — dispara una corrida real
contra Supabase (con red real), y consume minutos reales de GitHub
Actions.

- [ ] **Step 1: Confirmar con la persona antes de disparar**

Preguntar explícitamente: "¿disparo el workflow ahora a mano para
probar el despliegue, en vez de esperar al cron de mañana?" Esperar un
sí. (Si la respuesta es "esperemos al cron", esta tarea queda pendiente
hasta que la persona confirme que ya corrió sola, o pida dispararla más
tarde.)

- [ ] **Step 2: Disparar**

```bash
gh workflow run recolectar.yml
```

- [ ] **Step 3: Seguir la corrida**

```bash
gh run watch
```

(Si pide elegir cuál correr, elegir la más reciente de
`recolectar.yml`.) Esto se queda mostrando el progreso en vivo hasta que
termina — puede tardar hasta cerca de una hora si el presupuesto de 45
minutos se usa entero.

- [ ] **Step 4: Verificar el resultado contra Supabase**

```powershell
$env:POSTGRES_URL = "..."  # misma cadena de la Tarea 1
$env:POSTGRES_PASSWORD = "..."
.venv\Scripts\python.exe -c "
import db
eng = db.engine()
print('ofertas:', db.escalar(eng, 'SELECT COUNT(*) FROM ofertas'))
print('terminos:', db.escalar(eng, 'SELECT COUNT(*) FROM terminos_busqueda'))
"
Remove-Item Env:\POSTGRES_URL
Remove-Item Env:\POSTGRES_PASSWORD
```

Esperado: `terminos` en 26 (el seed corrió), `ofertas` mayor a 0 (algo se
recolectó de verdad, aunque sea parcial — el presupuesto de 45 minutos no
necesariamente alcanza para las 26 en una sola corrida, como ya se vio
al sembrar la base local).

---

### Task 5: Desplegar en Streamlit Cloud

**No delegable ni siquiera a la sesión principal** — requiere que la
persona autorice el acceso de Streamlit Cloud a su cuenta de GitHub, un
flujo de OAuth que nadie más puede completar por ella. Esta tarea es una
guía paso a paso para la persona, con verificación al final.

- [ ] **Step 1: Conectar el repo**

En [share.streamlit.io](https://share.streamlit.io), botón "New app" (o
"Create app"). Elegir el repo `buscador-empleo-personalizado` (privado —
puede pedir autorizar el acceso de Streamlit a los repos privados de la
cuenta de GitHub si todavía no se hizo). Rama: `main`. Archivo principal:
`app.py`.

- [ ] **Step 2: Configurar los secrets**

Antes de darle a "Deploy", en la sección "Advanced settings" (o
"Secrets", según la versión de la interfaz), pegar:

```toml
[conexion]
postgres_url = "postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx-1.pooler.supabase.com:5432/postgres"
password = "tu-contraseña-real"
```

(Mismo contenido que `.streamlit/secrets.toml` local — se puede abrir ese
archivo y copiar tal cual.)

- [ ] **Step 3: Deploy**

Confirmar el despliegue. Streamlit Cloud instala `requirements.txt` y
arranca la app — puede tardar unos minutos la primera vez.

- [ ] **Step 4: Verificar**

Abrir el link que da Streamlit Cloud. Comprobar:
- La pantalla de correo carga sin error.
- Entrar con un correo de prueba y guardar un perfil no tira ninguna
  excepción visible.
- Si la Tarea 4 ya corrió, "Ofertas para ti" muestra datos reales (no
  "todavía no hay ofertas").
- Ningún error de conexión a la base en pantalla (si `conexion.py` no
  encuentra bien los secrets, `db.engine()` cae a SQLite local — que en
  el contenedor de Streamlit Cloud es un archivo vacío que se crea al
  vuelo, así que el síntoma sería "todo funciona pero está vacío" en vez
  de un error explícito; comparar con lo que muestra `local` para
  confirmar que de verdad está leyendo Supabase).

**Si los secrets no se leen como se espera** (ver la sección 4 del spec
— es el único punto marcado como "se verifica de forma empírica"):
revisar si Streamlit Cloud expone lo pegado como archivo físico en
`.streamlit/secrets.toml` (que es lo que `conexion.py` espera) o solo vía
`st.secrets` en código. Si es lo segundo, `conexion.leer()` necesita un
tercer intento además de la variable de entorno y el archivo físico:

```python
def leer() -> dict:
    if os.environ.get("POSTGRES_URL"):
        return {"postgres_url": os.environ["POSTGRES_URL"],
                "password": os.environ.get("POSTGRES_PASSWORD", "")}
    if SECRETS.exists():
        datos = tomllib.loads(SECRETS.read_text(encoding="utf-8"))
        return datos.get("conexion") or {}
    try:
        import streamlit as st
        return dict(st.secrets.get("conexion", {}))
    except Exception:
        pass
    return {}
```

Esto solo se implementa si el Step 4 realmente muestra el síntoma — no
adelantarse a cambiar `conexion.py` sin haber confirmado el problema.

---

## Al terminar

`recolectar.py` corre solo, todos los días, contra una base que la app
en Streamlit Cloud también lee. El proyecto ya no depende de esta
máquina para nada salvo desarrollo.

**Pendiente, explícitamente fuera de alcance de este plan** (ya
documentado en el spec):
- Login real (`st.login()` con OIDC) y revisión del marco legal chileno
  de datos personales — condicionado a tener audiencia pública real.
- Monitoreo/alertas si el workflow falla — GitHub ya notifica por correo
  al dueño del repo por defecto, no se construye nada adicional.
