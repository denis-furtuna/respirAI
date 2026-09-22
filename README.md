# Arhitectură de Sistem și Design Mecanic: respirAI 
**Data:** Septembrie 2026 | **Locație:** Timișoara | **Status:** Masterplan Hackathon "Medical Renaissance"

## 1. Arhitectura de Bază (Creierul)
S-a renunțat complet la plăcile sclav (Arduino) pentru a salva spațiu, consum și cabluri. Totul rulează pe un singur microcontroller premium.
* **Microcontroller:** Seeed Studio XIAO ESP32-S3.
* **Avantaje critice:** Procesor Dual-Core, 8MB PSRAM (pentru Ring Buffer audio), conectivitate Bluetooth integrată, dimensiune minusculă, controller RMT hardware pentru LED-uri.
* **Management Energie:** Circuit de încărcare LiPo integrat nativ pe pad-urile de pe spatele plăcii (`BAT+` și `BAT-`). 

## 2. Bill of Materials (BOM) & Periferice
| Componentă | Protocol / Conexiune | Rol în Sistem | Observații |
| :--- | :--- | :--- | :--- |
| **INMP441** | I2S (3 pini logici) | Captare sunet pulmonar (Microfon MEMS) | Necesită etanșare acustică absolută. |
| **MAX30102** | I2C (2 pini logici) | Oximetru și senzor de puls | Montat în fanta ergonomică pentru arătător. |
| **AD8232** | Analog (1-3 pini) | Interfață EKG cu mufă Jack 3.5mm | Fixat pe standoffs cu șuruburi M2/M3. |
| **Matrice 8x8 WS2812B** | RMT (1 pin TX) | UI vizual (Ghidaj respirație) | Controlată via biblioteca `NeoPixelBus`. |
| **Baterie LiPo 3.7V** | Pad BAT | Sursă de energie | Cablul roșu secționat obligatoriu de un switch. |
| **Switch ON/OFF** | Fizic (Mecanic) | Oprirea generală a circuitului | Previne descărcarea completă a bateriei. |

## 3. Arhitectura Mecanică (Carcasa "Puck" Hibridă)
Dispozitivul este proiectat pentru a fi ținut în mâna stângă ca un joystick medical, în timp ce mâna dreaptă manipulează stetoscopul.

### 3.1. Zonele Funcționale ale Carcasei (CAD)
* **Fața Superioară (Top):** Matricea LED ascunsă sub un difuzor de lumină printat din PLA/PETG (grosime 0.4 - 0.6 mm, max 2 straturi).
* **Partea Inferioară (Bottom):** Adâncitură perfectă (0.2 mm) pentru aplicarea autocolantului tăiat cu logo-ul plămânilor.
* **Laterala 1 (Conectivitate EKG):** Orificiu pentru mufa Jack de la placa AD8232. Placa internă necesită cilindri de susținere (standoffs) solizi.
* **Laterala 2 (Ergonomie MAX30102):** Scobitură tip trăgaci unde cade natural degetul arătător. Senzorul privește direct spre buricul degetului.
* **Laterala 3 (Date/Încărcare):** Decupaj milimetric pentru portul USB-C al plăcii ESP32-S3 (care este ancorată de podeaua carcasei).
* **Laterala 4 (Power):** O fantă minusculă (5x2 mm) pentru lamela micro-întrerupătorului slide (ON/OFF).

### 3.2. Ansamblul Acustic (Inovația Hardware)
Nu se lipește cutia de piept! Sistemul folosește un furtun de stetoscop tăiat.
* **Ștuțul Acustic (Barb Fitting):** Un tub exterior proiectat pe carcasa principală, pe care se prinde etanș furtunul stetoscopului.
* **Camera de Compresie:** La interior, ștuțul se îngustează conic (pâlnie inversă) până la dimensiunea orificiului microfonului INMP441.
* **Etanșarea:** Placa microfonului se lipește sub presiune pe capătul pâlniei interne, folosind o garnitură inelară de silicon. Aerul lovește membrana, nu scapă în carcasă.

## 4. Arhitectura Software & Execuție
Se va folosi RTOS (Real-Time Operating System) nativ al ESP32 pentru a paralelizare.
* **Nucleul 0 (Core 0):** Preia exclusiv sarcina vizuală. Rulează animațiile de respirație pe matricea LED (prin `NeoPixelBus`), fără să întrerupă restul sistemului.
* **Nucleul 1 (Core 1):** Preia senzorii critici. Funcții: captura audio I2S (DMA continuu), citirea senzorilor (I2C/Analog) și stream-ul Bluetooth (împachetarea în Ring Buffer) către aplicația mobilă.

## 5. Branding și Finisaje Industriale
* **Cod Culori Text:** `respir` (Bleumarin / Navy Blue, font Regular) + `AI` (Cyan Electric Neon, font Extra Bold). Font sugerat: Montserrat / Inter.
* **Aplicare Logo:** Decalcomanie (waterslide decal) sau autocolant inkjet protejat cu lac transparent/bandă adezivă, printat la imprimanta de acasă Canon G3010 pe modul "High/Photo".
* **Ghidaj Pacient:** Telefonul conectat prin Bluetooth stă pe masă și oferă ghidajul topografic (unde să plaseze pacientul clopotul pe piept), în timp ce UI-ul luminos de pe carcasă ghidează ritmul respirator.
