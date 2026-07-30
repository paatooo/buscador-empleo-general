# Buscador de empleo personalizado — diseño

**Fecha:** 2026-07-29
**Estado:** diseño aprobado, sin implementar

## Objetivo

Una app donde cualquier persona en Chile — profesional o sin título —
obtenga un ranking de ofertas de trabajo contra su perfil, armando ese
perfil con un formulario en vez de editar un archivo a mano.

**Usuario objetivo:** cualquiera en Chile, con o sin título. Esta decisión
define todo el resto del diseño.

## Relación con `mapa-mercado-laboral`

Este proyecto nace de otro: `mapa-mercado-laboral`, una app de un solo
usuario que rankea ofertas contra un perfil fijo en YAML. **Son proyectos
totalmente independientes.** Nada se comparte:

| | `mapa-mercado-laboral` | Este proyecto |
|---|---|---|
| Repositorio | El suyo, ya existente | Uno propio y nuevo |
| Despliegue | Su app en Streamlit Cloud | App propia, URL propia |
| Base de datos | Su proyecto Supabase | Proyecto Supabase propio, esquema propio |
| Secretos | Los suyos | Credenciales propias, sin reutilizar ninguna |
| Código | Intacto, no se modifica | Escrito acá; a lo sumo se lee el otro como referencia |

No hay paquete compartido, ni imports cruzados, ni tablas compartidas, ni
despliegue coordinado. Los dos pipelines recolectan por su cuenta aunque
apunten a las mismas fuentes públicas. El costo consciente de esta decisión
es duplicación: un bug en la extracción de atributos habrá que arreglarlo
dos veces. Se acepta a cambio de que ninguno de los dos pueda romper al
otro.

La intención inicial era copiar su motor de matching tal cual y conectarle
un formulario. Al revisarlo contra el código real, tres supuestos no se
sostuvieron, y por eso el motor se reescribe en vez de copiarse:

1. **Su `matching.py` no es genérico.** `_CARGO_AFIN` está codificado a
   cargos de procesos y datos: cualquier otro oficio recibe
   `cargo_no_afin=True` y una penalización fija. `exclusion_flags` descarta
   ofertas de ingeniería eléctrica, que para un ingeniero eléctrico es justo
   lo que busca. Sus diccionarios `SKILLS` y `AREAS` cubren industria,
   procesos y datos, sin nada de salud, educación, retail, gastronomía,
   oficios ni comercio.

2. **El descarte del rubro plástico está incrustado en casi todo su
   `app_data.py`** — en `kpis`, `nuevas_alto_match`, `conteo_areas`,
   `conteo_habilidades`, `tendencias`, `radar_empresas` y
   `filtro_avanzado`. Esas funciones ni siquiera reciben el perfil, así que
   no había forma de "no tocarlas".

3. **Su tabla `oferta_analisis` mezcla lo genérico con lo personal.** Junto
   a habilidades y áreas guarda `cargo_no_afin`, el descarte `electrico` y
   el detalle del puntaje, todos dependientes de un perfil concreto.

Lo que sí se toma como referencia, sin importarlo: el patrón de motor de
base de datos y esquema cacheados por proceso (fue la lección de
rendimiento más cara de aquel proyecto: de 3-4s a ~230ms por operación), la
extracción de atributos del aviso (región, modalidad, tipo de contrato,
años de experiencia), y las fuentes de scraping.

## Decisiones tomadas

| Decisión | Elección | Alternativas descartadas |
|---|---|---|
| Usuario objetivo | Cualquiera en Chile, con o sin título | Solo perfiles técnicos; solo círculo cercano |
| Modelo de match | Cargo primero, habilidades después | Ampliar el diccionario a mano; puntuar todo con IA; híbrido cargo + IA |
| Recolección | Mixta: ~30 términos base curados + los cargos que aporten los usuarios | Solo dirigida por usuarios; catálogo amplio precargado |
| Relación entre apps | Proyecto nuevo y separado en todo — repo, despliegue, base de datos y motor propios | Generalizar el repo existente; motor compartido en un paquete; reusar la misma base de datos |
| Identidad | Solo correo, sin contraseña; login OIDC cuando escale | Login con Google desde el principio; enlace secreto sin cuenta |
| Cargo sin datos | Búsqueda en vivo al registrarse, con espera (más mensaje honesto si vuelve vacía, que es un resultado posible, no una ruta alternativa) | Solo avisar y esperar la corrida siguiente |

## Arquitectura

### 1. Motor de match "cargo primero"

Es la pieza que se escribe desde cero. El enfoque heredado puntuaba "qué
porcentaje de las habilidades pedidas tenés"; acá el cargo manda.

**El perfil declara:**

- `cargos_buscados` — texto libre, uno o varios ("cajero", "asistente
  contable", "ingeniero de procesos")
- `habilidades` — opcional, del catálogo o escritas libremente
- `anios_experiencia`
- `region` y si acepta remoto
- `evitar` — rubros o palabras que la persona no quiere ver

**El puntaje se arma con tres capas:**

1. **Afinidad de cargo (señal dominante).** Compara los cargos buscados
   contra el título del aviso, ambos normalizados, por coincidencia de
   palabras significativas. "Cajero/a supermercado turno tarde" contra
   "cajero" da afinidad alta; contra "ingeniero de procesos" da cero.
   Implementación: `difflib` de la biblioteca estándar más comparación de
   tokens. Sin dependencias nuevas.
2. **Habilidades (refinamiento).** Suman cuando el aviso pide algo que la
   persona tiene. **Nunca anulan el puntaje**: si el aviso no menciona
   ninguna habilidad, el score sigue siendo válido porque se sostiene en el
   cargo. Este es exactamente el caso que rompe el enfoque heredado, donde
   un aviso de reponedor o guardia produce un puntaje nulo.
3. **Ajustes duros.** Región incompatible, inglés excluyente, seniority muy
   por encima de la experiencia declarada, y los términos de `evitar`.

No existe una noción global de "cargo afín" ni descartes de rubro
codificados: la afinidad sale del perfil de cada usuario, y lo que cada
quien quiere evitar vive en su propia lista.

**Umbral de visibilidad: un solo número.** Por debajo de cierta afinidad la
oferta no se muestra — es ruido, no un match malo. El umbral se aplica sobre
**la afinidad de cargo sola, nunca sobre el puntaje final**: si se aplicara
al total, una oferta de otro rubro podría colarse por sumar en habilidades y
ubicación. El estado vacío deja de ser una regla aparte y pasa a ser una
consecuencia: si la lista filtrada queda sin nada, se muestra el mensaje
honesto.

Punto de partida: el equivalente a "al menos la mitad de las palabras
significativas del cargo buscado aparecen en el título". Va como **una sola
constante, marcada explícitamente como provisional**, para calibrarla contra
datos reales apenas haya usuarios. Cualquier valor elegido ahora es
inventado; lo que importa es que esté en un solo lugar y se sepa que lo es.

**Organización del código.** Cuatro piezas con responsabilidades separadas,
todas puras y testeables sin base de datos:

- afinidad de cargo (título del aviso contra cargos buscados)
- detección de habilidades (catálogo + extracción por regex)
- atributos del aviso (región, modalidad, tipo de contrato, años de
  experiencia)
- combinación final del puntaje

### 2. Datos

**Las ofertas son compartidas entre todos los usuarios.** Un solo pipeline;
el mercado es el mismo para todos. Esto es lo que hace viable el proyecto:
no hacen falta N pipelines de scraping, hace falta uno y N perfiles que lo
consulten.

**`oferta_analisis` guarda solo lo que no depende de nadie:** habilidades
detectadas, áreas, región, modalidad, tipo de contrato, años de experiencia
pedidos, si el inglés es excluyente, si es duplicada y la vigencia estimada.
No guarda ningún puntaje.

**El match se calcula al vuelo**, por usuario, sobre el DataFrame ya
cargado. Recorrer ~900 filas toma décimas de segundo y la afinidad de cargo
es más barata que las regex de habilidades. Nada nuevo que persistir.

**Esquema:**

```sql
CREATE TABLE usuarios (
  id TEXT PRIMARY KEY,           -- correo
  perfil_json TEXT,
  creado_en TEXT
);

CREATE TABLE marcas (
  usuario_id TEXT, job_url TEXT,
  revisada INTEGER, favorita INTEGER, postulada INTEGER, fecha TEXT,
  PRIMARY KEY (usuario_id, job_url)
);

CREATE TABLE terminos_busqueda (
  termino TEXT PRIMARY KEY,
  origen TEXT,                   -- 'base' | 'usuario'
  agregado_en TEXT,
  ultima_corrida TEXT,           -- para no re-scrapear lo recién buscado
  ofertas_ultimas INTEGER        -- para despriorizar términos estériles
);
```

Más las tablas de ofertas, snapshots y análisis, equivalentes a las del
proyecto de referencia.

El motor de base de datos y la verificación de esquema van **cacheados por
proceso** desde el primer día. Sin eso, cada consulta reconecta y
reinspecciona el catálogo, y la app se vuelve inusable en la nube.

### 3. Recolección

La lista de búsquedas vive en `terminos_busqueda`, no en el código. Arranca
con unas 30 ocupaciones frecuentes en Chile, mezclando con y sin título,
para que nadie entre a una app vacía. Cuando alguien declara un cargo que no
está, se agrega y entra en la corrida siguiente.

30 términos no son 30 ocupaciones: cada uno trae ~50 resultados por sitio y
los portales hacen su propia expansión difusa ("vendedor" arrastra ejecutivo
comercial, asesor de ventas, promotor). Aun así quedarán sectores enteros
afuera hasta que alguien los pida.

**Presupuesto de tiempo, no tope de términos.** Un límite por cantidad
(digamos 40) falla mal: si llegan 60 usuarios con cargos distintos, 20 nunca
ven datos frescos y no hay forma de saber cuáles. En cambio, un presupuesto
de ~45 minutos por corrida, procesando en orden de prioridad:

1. términos aportados por usuarios que nunca se han corrido
2. términos base
3. el resto, rotando entre corridas

Así el crecimiento no rompe la corrida — solo hace que cada término se
refresque menos seguido, que es una degradación mucho más sana. Y da una
métrica útil para mostrar en la app: hace cuántos días se actualizó el cargo
de cada persona.

Se despriorizan los términos que llevan varias corridas sin devolver nada, y
no se re-scrapea un término buscado hace poco.

**La lista base de ~30 ocupaciones se deriva de las categorías que publican
los propios portales** (Trabajando, Computrabajo y Laborum las exponen con
el número de avisos en cada una). Esa es la señal correcta: es el inventario
que efectivamente vamos a scrapear, no una estimación del empleo nacional,
que incluye mucho trabajo que nunca se publica en portales.

Borrador de bloques a cubrir mientras se valida contra esos datos — **no
verificado, tratar como punto de partida**: ventas y retail (vendedor,
cajero, reponedor), administración (asistente administrativo, recepcionista,
asistente contable), logística y transporte (bodeguero, conductor),
servicios (guardia de seguridad, auxiliar de aseo, garzón, cocinero), salud
(TENS, enfermera), educación (profesor, educadora de párvulos), construcción
y oficios (maestro, eléctrico, soldador), industria (operario de producción,
supervisor de producción, mantención), tecnología (desarrollador, soporte
TI, analista de datos) y atención al cliente (call center).

Conviene no sobreinvertir acá: como hay búsqueda en vivo al registrarse, el
único trabajo de la lista base es que la app no se vea vacía para quien
entra a mirar antes de armar su perfil. No necesita ser representativa del
mercado, solo voluminosa y variada.

### 4. Búsqueda en vivo al registrarse

Cuando alguien guarda un perfil con un cargo que la base no cubre, la app
scrapea ese término en el momento, con barra de progreso, y analiza las
ofertas nuevas antes de mostrarlas.

**Restricción de fuentes.** Indeed y LinkedIn vía JobSpy bloquean IPs de
datacenter, y Streamlit Cloud es exactamente eso. La búsqueda en vivo solo
puede usar Get on Board, Trabajando, Laborum y Computrabajo. Las otras dos
quedan para la corrida programada. Hay que decírselo al usuario: lo que ve
al registrarse es una primera pasada, y al día siguiente habrá más.

**Tope de 30 segundos en total, con resultados parciales.** Las fuentes
tienen velocidades muy distintas — Get on Board es una API y responde en
segundos, Computrabajo es scraping de HTML y es la más lenta. Se corren en
orden de rapidez y se muestra lo que haya llegado cuando se acaba el tiempo.
Que la primera pasada sea incompleta no es un problema, porque al usuario ya
se le avisa que mañana habrá más; un registro que tarda un minuto sí lo es.

**El caso vacío sigue existiendo.** Si el cargo no tiene ofertas publicadas
esta semana, la búsqueda en vivo devuelve cero. Cuando nada supera el umbral
de afinidad, se muestra un mensaje honesto ("todavía no tenemos ofertas de
X, las seguimos buscando") en vez de una lista de match 10, que parece una
app rota más que datos faltantes.

**Guardarraíles:** límite de búsquedas en vivo simultáneas, y reutilización
de lo ya recolectado para términos recientes.

### 5. La app

Streamlit, con estas pestañas: Ofertas para ti, Filtro avanzado, Tendencias,
Empresas, Acerca de los datos. Más la pantalla de correo y el formulario de
perfil (cargos buscados, habilidades, años, región/remoto, qué evitar).

Queda fuera de la primera versión una pestaña de "Qué estudiar": exige un
diccionario de cerrabilidad de brechas por ocupación, que es curación grande
y no es lo que valida el producto.

Todo widget necesita `key=` único con prefijo por pestaña: Streamlit ejecuta
el código de todas las pestañas en cada rerun y dos widgets con el mismo
label chocan. Es un error que ya costó dos veces en el proyecto de
referencia, y pytest no lo detecta — hay que probar con `streamlit run`
antes de desplegar.

## Privacidad y alcance

Mientras la identificación sea solo correo sin contraseña, **la app no se
difunde públicamente**: cualquiera podría escribir el correo de otro y ver
su perfil y sus postulaciones. Antes de abrirla a desconocidos hay que
agregar login real (`st.login()` con OIDC) y verificar el marco legal
chileno de datos personales — rige la Ley 19.628, y la Ley 21.719, que crea
la agencia de protección de datos, entraría en vigencia por estas fechas.
Confirmar antes de publicar; no darlo por sentado.

No se guardan CV en esta fase.

## Pruebas

El motor es puro y testeable sin base de datos. Casos que importan:

- oficios sin habilidades detectables — el score debe ser válido, no nulo
- cargo exacto contra parcial contra sin relación
- perfil sin habilidades declaradas
- la lista `evitar` de una persona no afecta lo que ve otra
- las marcas de un usuario no se filtran a otro
- un término buscado hace poco no se vuelve a scrapear
- el presupuesto de tiempo corta la corrida sin dejar la base inconsistente

## Fuera de alcance

- Parser de CV con IA — la parte más cara y con más superficie de error.
  Después de validar que el resto funciona.
- Puntuación con IA sobre el top de resultados.
- Multi-tenancy (organizaciones, roles, permisos).
- Pestaña "Qué estudiar".
- Notificaciones cuando aparece una oferta de alto match.
