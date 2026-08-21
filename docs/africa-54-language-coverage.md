# Africa-54 language coverage

Muta's internal catalog maps **85 candidate written languages across all 54 fully recognised
African sovereign states**. Settings exposes the interface-ready subset by autonym: every visible
explicit choice changes both the menus and the next response preference. Registry languages that
still lack an accepted complete catalog remain in backend code and this planning matrix, but stay
off the learner-facing selector until support becomes available.

## Scope and method

The country boundary follows the [UN Statistics Division M49 Africa
grouping](https://unstats.un.org/unsd/methodology/m49/overview/). The [African Union lists 55
members](https://www.au.int/en/member_states/countryprofiles2) because it also includes the
Sahrawi Arab Democratic Republic; Muta's Africa-54 gate follows the user's requested 54 fully
recognised states.

Language selection starts from [Unicode CLDR's territory-language
information](https://www.unicode.org/cldr/charts/49/supplemental/territory_language_information.html),
which focuses on literate populations able to use a language with computers and records
official status. The baseline also includes principal national lingua francas so a colonial
official language never counts as a multilingual country's only representation.

The candidate rule is: nationally official or working written languages with a country-wide
function, plus languages at 20% or more in CLDR territory data, plus specifically documented
country-wide lingua francas. It does not mean every constitutionally listed, regional, or
minority language. Regional spoken Arabic varieties are mapped to the standard written Arabic
interface locale at this stage; script or regional variants can become separate packs after
community review. The current matrix is a draft product artifact: edge-level sources and regional
or native-speaker review are still required before it can be called the final “main language” set.

## Country matrix

Language tags are BCP 47 / ISO identifiers. Their autonyms and writing directions live in
`ui/africa-languages.js`, the executable source of truth checked by the UI test suite.

| Country | ISO | Main written-language baseline |
|---|---:|---|
| Algeria | DZ | ar, kab, fr |
| Angola | AO | pt, umb, kmb |
| Benin | BJ | fr, fon |
| Botswana | BW | en, tn |
| Burkina Faso | BF | fr, mos, dyu |
| Burundi | BI | rn, fr, en |
| Cabo Verde | CV | pt, kea |
| Cameroon | CM | fr, en, wes, ff |
| Central African Republic | CF | sg, fr |
| Chad | TD | ar, fr |
| Comoros | KM | zdj, wni, wlc, ar, fr |
| Republic of the Congo | CG | fr, ln, mkw |
| Democratic Republic of the Congo | CD | fr, ln, sw, lua, kg |
| Djibouti | DJ | so, aa, ar, fr |
| Egypt | EG | ar |
| Equatorial Guinea | GQ | es, fan, fr, pt |
| Eritrea | ER | ti, ar, en |
| Eswatini | SZ | ss, en |
| Ethiopia | ET | am, om, so, ti, aa, en |
| Gabon | GA | fr, fan |
| The Gambia | GM | en, mnk, wo, ff |
| Ghana | GH | en, ak, ee, dag |
| Guinea | GN | fr, ff, sus, man |
| Guinea-Bissau | GW | pt, pov |
| Côte d’Ivoire | CI | fr, dyu, bci |
| Kenya | KE | sw, en |
| Lesotho | LS | st, en |
| Liberia | LR | en, kpe, lir |
| Libya | LY | ar |
| Madagascar | MG | mg, fr |
| Malawi | MW | ny, en |
| Mali | ML | bm, ff, ses, fr |
| Mauritania | MR | ar, ff, snk, wo |
| Mauritius | MU | mfe, fr, en |
| Morocco | MA | ar, zgh, fr |
| Mozambique | MZ | pt, vmw, ts |
| Namibia | NA | en, kj, ng, af, naq |
| Niger | NE | ha, dje, ttq-Latn, fr |
| Nigeria | NG | en, pcm, ha, yo, ig |
| Rwanda | RW | rw, en, fr, sw |
| São Tomé and Príncipe | ST | pt, cri |
| Senegal | SN | wo, fr, ff, srr |
| Seychelles | SC | crs, en, fr |
| Sierra Leone | SL | kri, en, men, tem |
| Somalia | SO | so, ar |
| South Africa | ZA | zu, xh, af, en, nso, tn, st, ts, ss, ve, nr |
| South Sudan | SS | en, pga-Latn, din, nus |
| Sudan | SD | ar, en |
| Tanzania | TZ | sw, en |
| Togo | TG | fr, ee, kbp |
| Tunisia | TN | ar, fr |
| Uganda | UG | en, sw, lg |
| Zambia | ZM | en, bem, ny, toi, loz |
| Zimbabwe | ZW | sn, nd, en |

## Readiness rule

- **Mapped:** present in the internal draft registry for backend and planning use.
- **Interface-ready:** every required UI message is translated and has passed the mechanical
  acceptance gates, so it is visible in Settings and localizes the browser chrome.
- **Hidden:** retained in the registry but omitted from Settings because no exact translation source
  passed the current gates. It can become visible without changing the backend language contract.
- **Reviewed:** translation/community-review metadata has been recorded internally for the pack;
  review status is not shown in the learner-facing selector.
- **Additional:** scheduled only after the Africa-54 baseline is mapped; it always appears
  after the baseline in the catalog.

Written UI localization cannot honestly represent a sign language. Sign-language access needs
visual-language content and interaction support, so it remains a separate accessibility workstream
rather than a misleading text option.
