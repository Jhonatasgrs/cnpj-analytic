# Metodologia de Análise de Mobilidade de Porte das Empresas (2023 ➔ 2026)

Este documento descreve detalhadamente a metodologia, regras de negócio, modelagem matemática, arquitetura SQL e interpretação estatística utilizadas no estudo de transição de porte das empresas brasileiras entre o fechamento de 2023 (`2023-12`) e meados de 2026 (`2026-06`), processados com **DuckDB** e **Pandas** a partir dos microdados oficiais da Receita Federal do Brasil (RFB).

---

## 1. Regras de Negócio e Classificação da RFB

Na estrutura de dados abertos de CNPJ da Receita Federal, o atributo `porte_empresa` da tabela `empresas` segue a classificação baseada na **Lei Complementar nº 123/2006 (Estatuto Nacional da Microempresa e da Empresa de Pequeno Porte)**:

| Código | Denominação RFB | Critério Legal / Operacional de Faturamento Anual |
| :---: | :--- | :--- |
| **`01`** | **Não Informado / Demais** | Empresas de Médio e Grande Porte, empresas não optantes do Simples Nacional submetidas ao Lucro Presumido/Real, ou registros onde o porte não é exigido/aplicável. |
| **`03`** | **Microempresa (ME)** | Receita bruta igual ou inferior a **R$ 360.000,00** ao ano. |
| **`05`** | **Empresa de Pequeno Porte (EPP)** | Receita bruta superior a **R$ 360.000,00** e igual ou inferior a **R$ 4.800.000,00** ao ano. |
| **`00` / `NULL`** | **Não Informado** | Registros cadastrais legados ou sem classificação ativa. |

### 1.1. Matriz de Mobilidade de Porte
A mobilidade entre 2023 e 2026 foi categorizada da seguinte forma:

* **Evolução de Porte**:
  * `01 ➔ 03` e `01 ➔ 05`: Regularização/enquadramento formal ou crescimento.
  * `03 ➔ 05`: **Ascensão de porte pura (ME para EPP)**, indicando superação do teto de R$ 360 mil de faturamento anual.
* **Regressão de Porte**:
  * `05 ➔ 03`: **Redução de porte (EPP para ME)**, indicando contração de receita para patamares abaixo de R$ 360 mil.
  * `05 ➔ 01` e `03 ➔ 01`: Desenquadramento ou mudança estrutural de regime societário.
* **Estagnação**:
  * `01 ➔ 01`, `03 ➔ 03`, `05 ➔ 05`: Empresas que permaneceram no mesmo porte ao longo dos 2,5 anos analisados.
* **Outros**:
  * Transições envolvendo registros nulos (`00` ou `NULL`).

---

## 2. Fórmulas Matemáticas e Indicadores Estatísticos

Para mensurar as transformações de forma comparável e imune a distorções de tamanho amostral, aplicaram-se as seguintes formulações:

### 2.1. Taxas Globais de Transição
Sendo $N$ o total de empresas presentes simultaneamente em 2023 e 2026 ($N = 55.911.128$):

$$\text{Taxa de Evolução Global (\%)} = \left( \frac{\sum \text{Evoluções}}{N} \right) \times 100 = \frac{167.075}{55.911.128} \times 100 \approx 0,30\%$$

$$\text{Taxa de Regressão Global (\%)} = \left( \frac{\sum \text{Regressões}}{N} \right) \times 100 = \frac{22.561}{55.911.128} \times 100 \approx 0,04\%$$

$$\text{Taxa de Estagnação Global (\%)} = \left( \frac{\sum \text{Estagnadas}}{N} \right) \times 100 = \frac{55.653.003}{55.911.128} \times 100 \approx 99,54\%$$

### 2.2. Razão de Dinamismo Empresarial ($R_{din}$)
Mede a proporção de empresas que avançam de porte para cada empresa que retrocede:

$$R_{din} = \frac{\text{Volume de Evoluções}}{\text{Volume de Regressões}} = \frac{167.075}{22.561} \approx 7,41\times$$

*Para cada 1 empresa que regrediu de porte no Brasil entre 2023 e 2026, 7,41 empresas evoluíram.*

### 2.3. Taxa Setorial de Mobilidade (por CNAE)
Para cada subclasse CNAE $i$:

$$\text{Taxa de Evolução}_{i} = \left( \frac{\text{Evoluções}_{i}}{\text{Total de Empresas Comparáveis no CNAE}_{i}} \right) \times 100$$

$$\text{Taxa de Regressão}_{i} = \left( \frac{\text{Regressões}_{i}}{\text{Total de Empresas Comparáveis no CNAE}_{i}} \right) \times 100$$

> **Critério de Significância Estatística:** Para o ranking de taxas setoriais, estabeleceu-se um filtro de corte de no mínimo **1.000 empresas ativas na base comparável**, evitando que subclasses com pouquíssimas unidades (ex: 2 empresas onde 1 evoluiu) gerassem taxas espúrias de 50% ou 100%.

### 2.4. Concentração Temporal e Idade da Empresa
A idade da empresa na data de corte da análise (2026) é dada por:

$$\text{Idade} = 2026 - \text{Ano}(\text{data\_inicio\_atividade})$$

As coortes etárias foram agrupadas em:
1. **Até 3 anos (Jovem / Start)**: Abertas entre 2023 e 2026.
2. **4 a 7 anos (Fase de Escala / Crescimento)**: Abertas entre 2019 e 2022.
3. **8 a 15 anos (Consolidação)**: Abertas entre 2011 e 2018.
4. **16 a 25 anos (Madura)**: Abertas entre 2001 e 2010.
5. **Mais de 25 anos (Tradicional)**: Abertas até 2000.

---

## 3. Arquitetura das Consultas SQL (CTEs no DuckDB)

As consultas foram estruturadas em Common Table Expressions (CTEs) executadas diretamente no motor analítico colunar do DuckDB:

```sql
-- 1. Identificação do Fluxo de Transição
WITH empresas_comparaveis AS (
    SELECT 
        e23.cnpj_basico,
        COALESCE(e23.porte_empresa, '00') AS porte_2023,
        COALESCE(e26.porte_empresa, '00') AS porte_2026,
        CASE 
            WHEN (COALESCE(e23.porte_empresa, '00') = '01' AND COALESCE(e26.porte_empresa, '00') IN ('03', '05'))
              OR (COALESCE(e23.porte_empresa, '00') = '03' AND COALESCE(e26.porte_empresa, '00') = '05') THEN 'Evolução'
            WHEN (COALESCE(e23.porte_empresa, '00') = '05' AND COALESCE(e26.porte_empresa, '00') IN ('01', '03'))
              OR (COALESCE(e23.porte_empresa, '00') = '03' AND COALESCE(e26.porte_empresa, '00') = '01') THEN 'Regressão'
            WHEN COALESCE(e23.porte_empresa, '00') = COALESCE(e26.porte_empresa, '00') THEN 'Estagnado'
            ELSE 'Outros'
        END AS categoria_transicao
    FROM empresas e23
    JOIN empresas e26 
      ON e23.cnpj_basico = e26.cnpj_basico 
     AND e26.ano_referencia = 2026
    WHERE e23.ano_referencia = 2023
)
```

Para o enriquecimento de perfil (setorial, regional e temporal):
1. **Filtro da Matriz**: `identificador_matriz_filial = '1'` e `ano_referencia = 2026` na tabela `estabelecimentos`, garantindo que os dados de localização e atividade principal correspondam à sede da pessoa jurídica.
2. **Lookup em Tabelas de Domínio**: `LEFT JOIN` com as tabelas `municipios` e `cnaes` (ano 2026) pelo código de 4 e 7 dígitos, respectivamente.

---

## 4. Síntese dos Resultados e Principais Insights

### 4.1. Panorama Geral
* **55,65 milhões de empresas (99,54%)** permaneceram com o mesmo enquadramento de porte.
* **167.075 empresas (0,30%)** apresentaram evolução de porte.
* **22.561 empresas (0,04%)** apresentaram regressão de porte.
* A transição ascendente mais expressiva foi `01 ➔ 03` (115.800 empresas), seguida por `01 ➔ 05` (30.290 empresas) e a progressão direta de ME para EPP `03 ➔ 05` (20.985 empresas).

### 4.2. Perfil Setorial (CNAEs com Maior Taxa de Evolução)
Os setores que demonstraram maior dinamismo de crescimento e formalização foram:
1. **4622-2/00 - Comércio atacadista de soja**: **5,04%** de taxa de evolução (117 evoluções em 2.321 empresas).
2. **2731-7/00 - Fabricação de aparelhos e equipamentos para distribuição e controle de energia elétrica**: **3,86%** (92 em 2.384).
3. **4211-1/02 - Pintura para sinalização em pistas rodoviárias e aeroportos**: **3,63%** (41 em 1.131).
4. **4645-1/01 - Comércio atacadista de instrumentos e materiais para uso médico e hospitalar**: **3,46%** (551 em 15.944).
5. **2093-2/00 - Fabricação de aditivos de uso industrial**: **3,12%** (49 em 1.571).
6. **4662-1/00 - Comércio atacadista de máquinas e equipamentos para terraplenagem e construção**: **3,10%** (57 em 1.839).
7. **6110-8/03 - Serviços de comunicação multimídia (SCM - Provedores de Internet)**: **3,07%** (671 em 21.891).
8. **4621-4/00 - Comércio atacadista de café em grão**: **2,99%** (128 em 4.286).
9. **4683-4/00 - Comércio atacadista de defensivos agrícolas, adubos e fertilizantes**: **2,95%** (397 em 13.465).

> **Insight:** O **Agronegócio** e a cadeia de suprimentos de bens industriais/médicos e infraestrutura de telecomunicações lideram a proporção de empresas em expansão econômica.

### 4.3. Perfil Regional
* **Estados Líderes em Volume de Evolução:**
  1. **São Paulo (SP)**: 36.489 empresas (taxa: 0,23%)
  2. **Minas Gerais (MG)**: 15.542 empresas (taxa: 0,25%)
  3. **Paraná (PR)**: 14.864 empresas (taxa: 0,39%)
  4. **Santa Catarina (SC)**: 13.461 empresas (**taxa de destaque: 0,52%**)
  5. **Rio Grande do Sul (RS)**: 10.159 empresas (taxa: 0,26%)

* **Municípios Líderes em Volume de Evolução:**
  1. São Paulo (SP): 12.889
  2. Manaus (AM): 3.856
  3. Rio de Janeiro (RJ): 3.637
  4. Curitiba (PR): 3.446
  5. Belo Horizonte (MG): 3.083
  6. Brasília (DF): 2.928
  7. Goiânia (GO): 2.758
  8. Cuiabá (MT): 2.066
  9. Porto Alegre (RS): 1.683
  10. Campo Grande (MS): 1.513

### 4.4. Efeito Coorte e Ciclo de Vida da Empresa
A análise por ano de início de atividade revela um padrão nítido de ciclo de vida corporativo:

| Faixa Etária (em 2026) | Evoluções | Regressões | Total Transições | Razão Evolução / Regressão |
| :--- | :---: | :---: | :---: | :---: |
| **1. Até 3 anos (Jovem / Start)** | 17.280 | 1.223 | 18.503 | **14,13x** |
| **2. 4 a 7 anos (Crescimento / Escala)** | **59.902** | 4.153 | **64.055** | **14,42x** |
| **3. 8 a 15 anos (Consolidação)** | 50.883 | 7.466 | 58.349 | **6,82x** |
| **4. 16 a 25 anos (Madura)** | 24.703 | 5.083 | 29.786 | **4,86x** |
| **5. Mais de 25 anos (Tradicional)** | 14.307 | 4.632 | 18.939 | **3,09x** |

> **Conclusão Analítica:** A janela crítica de mobilidade ascendente ocorre entre o **4º e o 7º ano de atividade**. Empresas com menos de 7 anos possuem mais de **14 evoluções para cada 1 regressão**. Conforme a empresa amadurece (acima de 15 anos), a taxa de regressão proporcional aumenta consideravelmente, convergindo para uma razão de 3x.

---

## 5. Artefatos Gerados

### Tabelas Analíticas (`output/*.csv`)
* `fluxo_porte.csv`: Matriz completa de transição entre todos os pares de portes.
* `resumo_geral.csv`: Agrupamento consolidado (Evolução, Regressão, Estagnado).
* `cnae_evolucao_taxa_top10.csv`: Top 10 setores por taxa percentual de evolução.
* `cnae_evolucao_volume_top10.csv`: Top 10 setores por volume absoluto de evolução.
* `cnae_regressao_taxa_top10.csv`: Top 10 setores por taxa percentual de regressão.
* `cnae_regressao_volume_top10.csv`: Top 10 setores por volume absoluto de regressão.
* `uf_evolucao_top5.csv`: Top 5 estados por volume e taxa de evolução.
* `uf_regressao_top5.csv`: Top 5 estados por volume e taxa de regressão.
* `municipio_evolucao_top10.csv`: Top 10 municípios em evolução.
* `municipio_regressao_top10.csv`: Top 10 municípios em regressão.
* `cohort_idade.csv`: Matriz de transição por faixa etária da empresa.
* `ano_concentracao.csv`: Série histórica de transições por ano de abertura (2000 a 2023).

### Gráficos e Visualizações (`output/*.png`)
* `fluxo_transicao_porte.png`: Gráfico horizontal de barras demonstrando o volume de cada par de transição ativa.
* `perfil_setorial_cnae.png`: Painel comparativo dos Top 10 setores com maior taxa de evolução vs. regressão.
* `perfil_regional_evolucao.png`: Painel geográfico com o Top 5 UFs e Top 10 Municípios com maior volume de ascensão.
* `concentracao_ano_abertura.png`: Curvas temporais relacionando o ano de fundação da empresa com as taxas de transição de porte.
