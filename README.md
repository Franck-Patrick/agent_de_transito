# Agente Inteligente de Controle de Trânsito (G7)

Simulação de um cruzamento com semáforo controlado por um agente inteligente. A tela mostra o cruzamento ao vivo e, a cada tick, **o que o agente percebeu, qual regra usou e por quê**.

## Como rodar

Jeito mais simples (funciona de qualquer pasta, sem ativar nada):

```bash
~/proj_ai/run.sh                   # depois abra http://127.0.0.1:8000
```

Passo a passo manual:

```bash
python3 -m venv .venv && source .venv/bin/activate   # no macOS o comando é python3
pip install -r requirements.txt

uvicorn app.main:app --reload      # web: abrir http://127.0.0.1:8000
python -m agent.cli                # só terminal
python -m agent.cli -v --ticks 60  # terminal, todos os ticks
pytest                             # testes
```

Cartas surpresa pelo terminal:

```bash
python -m agent.cli --emergency-at 40:E --fail-sensor-at 70:N --repair-sensor-at 110:N --surge-at 20:W
```

## A ideia em uma frase

O semáforo é um "guarda de trânsito" que olha as filas (sensores), pensa com algumas regras em ordem de prioridade (agente) e só pode fazer uma coisa: trocar ou manter o sinal (atuador). Quanto mais carros passam e menos gente espera, melhor a nota dele (desempenho).

## Estrutura (espelha o PEAS)

| Letra | Arquivo | O que é |
|---|---|---|
| **P** Performance | [agent/performance.py](agent/performance.py) | Vazão, espera acumulada, espera de emergência, pontuação |
| **E** Environment | [agent/environment.py](agent/environment.py) | Cruzamento N/S/E/W, filas, chegadas aleatórias, semáforo de 2 fases |
| **A** Actuators | [agent/actuators.py](agent/actuators.py) | Semáforo: `KEEP` ou `SWITCH` (sempre passa pelo amarelo) |
| **S** Sensors | [agent/sensors.py](agent/sensors.py) | Laço indutivo por via (fila e espera, pode falhar), detector de sirene, leitura do sinal |
| Agente | [agent/agent.py](agent/agent.py) | Percepção -> decisão explicada |
| Ciclo | [agent/simulation.py](agent/simulation.py) | Um tick = sensores -> agente -> atuador -> ambiente -> desempenho |
| Terminal | [agent/cli.py](agent/cli.py) | Modo somente Python |
| Web | [app/main.py](app/main.py), [app/static/](app/static/) | FastAPI + WebSocket + canvas |

O front-end não decide nada: só desenha o que o Python manda.

## Como funciona, passo a passo

### O ciclo de um tick

Toda a aplicação gira em torno de uma unidade de tempo chamada tick, que podemos pensar como um segundo. A cada tick, o método `step()` de [agent/simulation.py](agent/simulation.py) executa sempre a mesma sequência, e essa sequência é o próprio ciclo de vida de um agente segundo Russell & Norvig: perceber, decidir, agir. Primeiro os sensores leem o cruzamento e montam uma percepção. Em seguida o agente recebe essa percepção e devolve uma decisão. O atuador executa a decisão no semáforo. Só então o ambiente avança um tick (chegam carros, o sinal evolui, carros saem) e, por último, a medida de desempenho contabiliza o que aconteceu. Repare que o agente decide olhando o mundo como ele estava *antes* do tick avançar, exatamente como um controlador real, que só conhece o passado imediato.

### O que o agente enxerga

O agente nunca acessa o ambiente diretamente. Ele não tem acesso às listas de carros nem ao gerador de números aleatórios. Tudo o que ele sabe chega pelo objeto `Percept`, montado em [agent/sensors.py](agent/sensors.py). Essa percepção contém, para cada uma das quatro vias, quantos carros estão parados e há quanto tempo está esperando o carro mais antigo da fila. Também diz em quais vias há uma sirene tocando e qual é o estado atual do semáforo (eixo com verde, fase verde ou amarela, tempo na fase). Essa separação é o que torna o ambiente parcialmente observável: quando a carta "sensor quebrado" é jogada, a via afetada passa a aparecer como `None` na percepção. O carro continua lá no ambiente, mas o agente simplesmente deixa de saber. O detector de sirene é um sensor separado, por isso o agente continua percebendo ambulâncias mesmo com o sensor de fila quebrado.

### O que o agente lembra

A primeira coisa que o agente faz em `decide()`, em [agent/agent.py](agent/agent.py), é atualizar seu estado interno no método `_update_model()`. Ele guarda duas informações: qual eixo estava verde na última vez que olhou (`last_axis`) e há quantos ticks esse verde está aberto (`green_time`). Se o eixo mudou, ele zera o contador; se a fase está verde, soma um. Esse contador é o "modelo do mundo" do agente, e é por causa dele que o classificamos como baseado em modelo e não como reativo simples: duas percepções idênticas podem levar a decisões diferentes dependendo de há quanto tempo o verde está aberto. Um agente reativo simples, sem essa memória, não conseguiria respeitar o verde mínimo nem o verde máximo.

### Como o agente decide

Com o modelo atualizado, o agente percorre uma lista de regras em ordem de prioridade, e a primeira que se aplica encerra a decisão. A ordem não é arbitrária: cada regra só faz sentido se as anteriores não se aplicaram.

A primeira verificação é se o semáforo está em amarelo. Se estiver, a troca já foi pedida e o agente não tem o que decidir, então mantém e espera. Em seguida vêm as emergências, porque salvar vidas vem antes de qualquer cálculo de eficiência. Se a ambulância está numa via que já tem verde, o agente segura o verde até ela passar, ignorando inclusive o verde máximo. Se ela está numa via com vermelho, o agente pede a troca na hora, mesmo que o verde atual tenha acabado de abrir. O amarelo continua obrigatório, porque o atuador não permite pular essa fase.

Depois o agente confere se algum sensor de fila falhou. Essa checagem precisa vir antes de qualquer conta, porque sem os números de uma via não dá para calcular a pressão. Nesse caso o agente entra em modo reserva e passa a se comportar como um semáforo comum de tempo fixo, trocando a cada 15 ticks. É uma degradação segura: ele perde eficiência mas não para de funcionar, e volta ao modo inteligente sozinho assim que o sensor é reparado.

Com os sensores em ordem, o agente calcula as métricas de cada eixo. A principal é a pressão, que é a soma, nas duas vias do eixo, do número de carros parados mais 0,2 vezes a maior espera. A espera entra na conta para que uma fila pequena mas esquecida há muito tempo também ganhe peso. Por exemplo, se a via N tem 3 carros e o mais antigo espera há 10 ticks, ela contribui com 3 + 2 = 5; se a via S tem 1 carro esperando há 4 ticks, contribui com 1,8; o eixo NS fica com pressão 6,8.

Com as métricas na mão, o agente aplica as regras de tempo e de eficiência. Se o verde está aberto há menos de 6 ticks, ele mantém, para evitar um semáforo que pisca o tempo todo e desperdiça tempo em amarelos. Se o verde já passou de 30 ticks e há alguém esperando do outro lado, ele troca, para que nenhum eixo fique esquecido mesmo quando o outro está sempre cheio. Se o eixo verde está vazio e o vermelho tem carros, ele troca, porque manter verde para ninguém é puro desperdício. Por fim vem a comparação de utilidade: se a pressão do eixo vermelho é mais de 1,5 vez a do verde, ele troca. A margem de 1,5 existe para que pequenas oscilações não provoquem trocas a todo momento. Continuando o exemplo, se o eixo EW tiver pressão 12, como 12 é maior que 6,8 x 1,5 = 10,2, o agente decide trocar pela regra `PRESSAO`. Se nada disso se aplicar, ele mantém o verde.

### Como a decisão é explicada

O agente não devolve só "troca" ou "mantém". Ele devolve um objeto `Decision` com quatro campos: a ação (`KEEP` ou `SWITCH`), o nome da regra que decidiu, um motivo escrito em português com os números daquele momento e as métricas usadas no cálculo. É esse objeto que aparece no painel "Raciocínio deste tick" da tela e nas linhas do modo terminal. A explicabilidade não é uma camada colada por fora: ela nasce no mesmo lugar em que a decisão é tomada, então o que a tela mostra é sempre o motivo real.

### Como a decisão vira ação

O atuador, em [agent/actuators.py](agent/actuators.py), é propositalmente simples. Se a ação é `SWITCH`, ele chama `start_yellow()` no ambiente; se é `KEEP`, não faz nada. Como só existem duas fases (NS e EW), o agente nunca precisa escolher *para qual* eixo ir, apenas *se* deve trocar. O ambiente, por sua vez, só aceita iniciar o amarelo se o sinal estiver verde, o que garante que um pedido repetido não bagunce a transição.

### Como o mundo reage

Quando o ambiente avança um tick, em [agent/environment.py](agent/environment.py), quatro coisas acontecem em ordem. Cada via sorteia se chega um carro novo (12% de chance, ou 35% durante um pico de tráfego); como o sorteio usa uma semente fixa, a mesma simulação se repete igual toda vez, o que facilita a apresentação. Depois o sinal evolui: se o amarelo já durou 2 ticks, o outro eixo ganha o verde. Em seguida, nas vias com verde, sai um carro a cada 2 ticks; a ambulância, quando está na frente da fila, sai assim que o verde abre. Por fim, todo carro que continua parado soma um tick de espera, e é esse número que os sensores vão ler no próximo ciclo.

### Como o desempenho é medido

Depois do tick, [agent/performance.py](agent/performance.py) registra quantos carros passaram, quanto tempo de espera se acumulou e quanto as ambulâncias esperaram, e calcula a pontuação. O agente não lê essa pontuação para decidir. Ela é a régua externa que diz se as regras dele estão boas. Se quisermos testar se outra margem de pressão ou outro verde mínimo funciona melhor, basta mudar a constante no topo de `agent.py` e comparar a pontuação final.

### Como as cartas surpresa entram

Os botões da tela (ou as opções `--emergency-at`, `--fail-sensor-at` e `--surge-at` do terminal) chamam métodos da `Simulation` que alteram o ambiente ou os sensores: colocam uma ambulância na fila, quebram o sensor de uma via ou aumentam a taxa de chegada. Nenhum deles fala com o agente. O agente descobre a novidade sozinho, pela próxima percepção, como aconteceria num cruzamento de verdade. Esse é um bom argumento para a apresentação: a reação à carta surpresa não foi programada como um "se apertar o botão, faça X", ela emerge das regras que o agente já tinha.

### Como a tela e o terminal mostram tudo

No modo web, [app/main.py](app/main.py) cria uma simulação própria para cada aba aberta e, em um laço, chama `step()` no ritmo escolhido (1,5 segundo por tick por padrão), enviando o resultado completo pelo WebSocket. Esse resultado inclui as filas, o semáforo, a percepção, a decisão e o desempenho. O [app/static/app.js](app/static/app.js) recebe esses dados e apenas desenha: anima os carros deslizando entre uma posição e outra, acende os semáforos e preenche os painéis. Não há nenhuma regra de trânsito no JavaScript. No modo terminal, [agent/cli.py](agent/cli.py) usa exatamente a mesma `Simulation`, só que em vez de desenhar, imprime uma linha por decisão. Por isso o comportamento do agente é idêntico nos dois modos.

## PEAS

- **P (desempenho):** `pontuação = carros que passaram - 0,1 x espera acumulada - 5 x espera de emergência`. Também medimos maior fila e número de trocas.
- **E (ambiente):** cruzamento de 4 vias, carros chegam aleatoriamente (12% de chance por tick por via, 35% em pico), 1 carro sai a cada 2 ticks por via com verde.
- **A (atuadores):** o sinal (manter ou trocar). Amarelo de 2 ticks obrigatório.
- **S (sensores):** tamanho da fila e maior espera por via, sirene por via, estado do semáforo.

## Propriedades do ambiente (Russell & Norvig)

| Propriedade | Classificação | Justificativa |
|---|---|---|
| Observabilidade | Parcialmente observável | Sensor pode falhar; o agente não sabe quantos carros vão chegar |
| Agentes | Agente único | Só o semáforo decide; motoristas são parte do ambiente |
| Determinismo | Estocástico | Chegadas de carros são aleatórias |
| Episódico/sequencial | Sequencial | Trocar agora afeta as filas dos próximos ticks |
| Estático/dinâmico | Dinâmico | Carros chegam mesmo enquanto o agente "pensa" |
| Discreto/contínuo | Discreto | Tempo em ticks, filas em números inteiros, 2 ações |
| Conhecido | Conhecido | As regras do cruzamento (amarelo, vazão) são conhecidas |

## Tipo de agente

**Baseado em modelo com utilidade simples.**

- **Modelo (estado interno):** o agente guarda há quanto tempo o verde atual está aberto (`green_time`). Isso não vem pronto do sensor: ele mesmo conta.
- **Utilidade:** compara a "pressão" dos dois eixos: `pressão = carros na fila + 0,2 x maior espera` (somado nas duas vias do eixo).

Não é reativo simples porque depende de memória (verde mínimo/máximo). Não é um agente de busca/planejamento porque não simula o futuro.

## As regras, em ordem de prioridade

A primeira que se aplica decide. O nome aparece na tela e no terminal.

1. `EM_TRANSICAO`: amarelo em andamento, nada a fazer.
2. `EMERGENCIA_NO_VERDE`: ambulância no eixo verde, segura o verde até passar.
3. `EMERGENCIA_NO_VERMELHO`: ambulância no eixo vermelho, troca já (ignora verde mínimo, mas respeita o amarelo).
4. `MODO_RESERVA`: algum sensor de fila falhou, usa tempo fixo de 15 ticks.
5. `VERDE_MINIMO`: verde há menos de 6 ticks, mantém (evita pisca-pisca).
6. `VERDE_MAXIMO`: verde há 30 ticks ou mais e alguém espera no vermelho, troca (evita que um eixo fique esquecido).
7. `VIA_VAZIA`: ninguém no verde e alguém no vermelho, troca.
8. `PRESSAO`: pressão do vermelho maior que 1,5x a do verde, troca.
9. `MANTER_VERDE`: nada justifica trocar.

Todos os números ficam no topo de [agent/agent.py](agent/agent.py) e [agent/environment.py](agent/environment.py), fáceis de mudar ao vivo.

## Cartas surpresa já tratadas

| Situação | Como o agente reage | Regra |
|---|---|---|
| Ambulância | Prioridade total; troca ou segura o verde | `EMERGENCIA_*` |
| Sensor quebrado | Cai para tempo fixo (degradação segura) | `MODO_RESERVA` |
| Pico de tráfego em uma via | A pressão sobe e o agente dá mais verde para ela, limitado pelo verde máximo | `PRESSAO`, `VERDE_MAXIMO` |

Para uma carta nova (ex.: acidente bloqueando uma via, pedestre, falta de energia), o roteiro de resposta é: qual letra do PEAS ela afeta, qual regra nova entraria e em que posição da prioridade.

## Simplificações (assumidas de propósito)

- 1 tick = 1 "segundo" conceitual.
- A ambulância fura a fila da sua via.
- Sem conversões, sem pedestres, uma faixa por via.
# agent_de_transitp
