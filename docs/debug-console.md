# Отладочная консоль и MMIO

Прошивка содержит полноценную отладочную консоль с ANSI-цветами. Вывод идёт
**не** через классический `SBUF`, а через регистры, отображённые в XDATA.

## Регистры

| Адрес | Направление | Назначение |
|---|---|---|
| `0xF072` | R | статус: `bit0` — готовность от видеоблока, `bit2`/`bit3` — TX ready двух каналов |
| `0xF073` | W | данные UART #0 |
| `0xF036` | R | статус UART #1 (`bit2` — TX ready) |
| `0xF037` | W | данные UART #1 |
| `0xF074` | R | данные от видеоблока |
| `0xBB00` | W | mailbox в сторону видеоблока |
| `0xFDF6` / `0xFDF7` | RW | командный mailbox: запрос `0x41`, ответ `0x81` |
| `0xF00A` | W | тестовый регистр (пишут `0x55`) |
| `0xD511` / `0xD510` | R | код события/состояния для wake-рутинны |
| `0xD5FD` / `0xD5FE` | RW | счётчики/статус, читаются таймерным ISR |

Цикл передачи (дизассемблер):

```
0x55A9  MOV  DPTR,#0xF072
0x55AC  MOVX A,@DPTR
0x55AD  JNB  ACC.2,0x55A9     ; ждём TX ready
0x55B0  MOV  DPTR,#0xF073
0x55B4  MOVX @DPTR,A
```

Скорость: в строках консоли есть переключение `UART3` на `115200` и `9600`,
рабочая — **115200 8N1**, 3.3 В TTL.

## Что печатает при загрузке

```
sr = 0
WSR
InitCop Start
ShareMemory Size : 0x1800
InitCop End
[S/W Version] M-A8000SGZA-1014.0
[Panel Info] I/F : 3, Res : 7, Vendor : 2, PBA : 0, PanelType : 0
[D1][SystemHPDControlOff] [HPD] Set HPD Low(channel:0x2, force:1)
```

Формат сообщений: `[0;33m…[0;m` — обычные ANSI-коды.

## Меню консоли

Строки из образа (порядок сохранён):

```
[Formal debug Menu]     1..5: OSD/MDHDLR/LINKHDLR/SYNCHDLR state, virtual key
[Custom debug Menu]     1 BFI, 2/3 baudrate, 4..8 DP out mode, 9 check,
                        10 skip checksum flag, 11 verify
[SecLib debug Menu]     Common / EDID / Factory / OSD / Picture / Screen /
                        Sound / Source / T-Con
[SecLib Source debug]   change source, check state, control hotplug,
                        CCG3 (PD) и RTS5411 (USB hub) диагностика
[Print level]           1..12 — фильтр вывода (essential, color, osd, modeHandler,
                        inputTiming, appEVT, compatibility, etc, tcon, sensor,
                        source, common)
shell>                  help / reboot / factory / remote / exit
```

Ввод защищён: `BINGO!!! MAGICKEY!!!! unlock serial input.` — последовательность
разблокировки ищется по коду (строкой она не лежит).

## Сервисное меню OSD

Вход (для мониторов с jog-кнопкой): открыть OSD, выставить `Brightness = 0` и
`Contrast = 0`, удерживать jog (ENTER/SOURCE) ~5 секунд до появления
`SERVICE FUNCTION MENU`.

Поля, которые оно показывает (из строк образа):

```
Version, Monitor On Time, Panel Ch. No., On Time, Cycle, Type, Scaler-MCU,
Panel Info, Checksum, PixelShift, Country, HotPlug Time, Mute Time, USB PORT,
Signal Noise Lv, Project Name, FlashEraseTimes, Store Mode, ERP, Off Timer Def.
```

Ничего в нём не менять, если цель — только прочитать состояние.
