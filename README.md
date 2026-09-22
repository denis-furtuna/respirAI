# Blueprint Mecanic & CAD: Carcasa respirAI
**Scop:** Manual de proiectare pentru execuția prin printare 3D a dispozitivului medical hibrid.

## 1. Conceptul Ergonomic Principal
Carcasa are forma unui "puc" sau a unui "mouse medical" supradimensionat. Se ține în mâna stângă. Baza se sprijină în palmă, degetul arătător se ancorează în laterala cu oximetrul (MAX30102), iar fața superioară luminoasă este orientată către ochii pacientului.

## 2. Topologia Externă (Zonele Funcționale)

### 2.1. Fața Superioară (UI & Branding)
* **Difuzorul LED:** Un decupaj central mare peste care vine montat capacul difuzor (printat la 0.4 - 0.6 mm grosime din filament alb/semitransparent) pentru a ascunde matricea WS2812B.
* **Branding:** O adâncitură de 0.5 mm cu textul *respirAI*, poziționată sub difuzorul LED. Literele pot fi umplute ulterior cu vopsea sau acoperite de un sticker taiat precis.

### 2.2. Fața Inferioară (Baza)
* **Punctul de Conexiune Acustică:** Fix în centrul bazei se proiectează ștuțul exterior (barb fitting) pe care se va mufează etanș furtunul tăiat al stetoscopului.
* **Zona Logo:** O adâncitură de 0.2 mm grosime, de formă pătrată/rotundă, destinată aplicării decalcomaniei cu plămânii, pentru a o proteja de frecarea cu suprafețele.

### 2.3. Lateralele (Conectivitate și Senzori)
* **Laterala Frontală/Dreapta (Trăgaciul):** O scobitură concavă, ergonomică, care ghidează natural degetul arătător. În centrul ei se află un orificiu dreptunghiular unde este expus senzorul MAX30102.
* **Laterala Stângă (Conectivitate EKG):** Un orificiu circular precis pentru mufa Jack de 3.5mm a plăcii AD8232.
* **Laterala Spate (Alimentare & Date):** 
    * Decupajul pentru portul USB-C al plăcii ESP32-S3.
    * O fantă laterală de 5x2 mm pentru comutatorul culisant (Slide Switch) de ON/OFF al bateriei.

## 3. Structurile Interne (Cable Management & Ancorare)

### 3.1. Camera Acustică de Compresie (Inovația)
* Se află pe interiorul feței inferioare, în continuarea ștuțului exterior.
* Este un canal care se îngustează sub formă de pâlnie întoarsă.
* **Etanșarea:** La capătul pâlniei interne, diametrul trebuie să se potrivească exact cu orificiul microfonului INMP441. Se proiectează un "pat" plat pentru placa INMP441, permițând fixarea ei sub presiune cu o garnitură inelară de silicon.

### 3.2. Punctele de Montare (Standoffs)
Fără prinderi mecanice, forța de a introduce o mufa Jack sau un cablu USB va distruge componentele.
* **Suport AD8232 (EKG):** 2 sau 4 piloni cilindrici (standoffs) cu diametrul interior potrivit pentru șuruburi M2 sau M3 (sau inserții filetate din alamă topite în plastic).
* **Suport ESP32-S3:** Piloni de sprijin sau șine de ghidaj pentru a ține placa rigidă când se inserează cablul USB-C.
* **Locaș Baterie LiPo:** Un compartiment delimitat de pereți subțiri de plastic (1-2 mm grosime) pentru a împiedica bateria să se lovească de pinii ascuțiți ai altor plăci în timpul manevrării.

## 4. Instrucțiuni de Printare 3D
* **Material:** PLA sau PETG (PETG recomandat pentru flexibilitate la montarea prin clipsare).
* **Grosime perete (Wall thickness/Perimeters):** Minim 3 perimetre (aprox. 1.2 mm) pentru rigiditate structurală când se apasă mufele.
* **Capacul Difuzor (Top):** Trebuie printat pe pat de sticlă sau PEI fin, fără suport, cu 100% infill pentru 2-3 straturi maxime, folosind filament de culoare deschisă.
