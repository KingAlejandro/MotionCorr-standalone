/***************************************************************************
 *
 * Author: "Sjors H.W. Scheres"
 * MRC Laboratory of Molecular Biology
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/
/***************************************************************************
 *
 * Authors:    J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
 *
 * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
 * 02111-1307  USA
 *
 *  All comments concerning this program package may be sent to the
 *  e-mail address 'xmipp@cnb.csic.es'
 ***************************************************************************/
#include "src/metadata_label.h"

//This is needed for static memory allocation
std::map<EMDLabel, EMDLabelData> EMDL::data;
std::map<std::string, EMDLabel> EMDL::names;
std::map<std::string, std::string> EMDL::definitions;
StaticInitialization EMDL::initialization; //Just for initialization

void EMDL::addLabel(EMDLabel label, EMDLabelType type, std::string name, std::string definition)
{
    data[label] = EMDLabelData(type, name);
    names[name] = label;
    definitions[name] = definition;
}

void EMDL::addAltLabel(EMDLabel label, std::string name)
{
    names[name] = label;
}

void EMDL::printDefinitions(std::ostream& out)
{
	out << "+++ RELION MetaDataLabel (EMDL) definitions: +++" << std::endl;
	std::map<std::string, std::string>::const_iterator strIt;

	for (strIt = definitions.begin(); strIt != definitions.end(); strIt++)
	{
		out << std::setw(30) <<strIt->first;

		if (EMDL::isInt(names[strIt->first]))
		{
			out << " (int)    ";
		}
		else if (EMDL::isBool(names[strIt->first]))
		{
			out << " (bool)   ";
		}
		else if (EMDL::isDouble(names[strIt->first]))
		{
			out << " (double) ";
		}
		else if (EMDL::isString(names[strIt->first]))
		{
			out << " (string) ";
		}
        else if (EMDL::isIntVector(names[strIt->first]))
        {
            out << " (vector<int>) ";
        }
		else if (EMDL::isDoubleVector(names[strIt->first]))
		{
			out << " (vector<double>) ";
		}
		else if (EMDL::isUnknown(names[strIt->first]))
		{
			out << " (string) ";
		}
		else
		{
			REPORT_ERROR("EMDL::printDefinitions: unrecognised type");
		}

		out << ": " << strIt->second <<std::endl;
	}
}


// The label registry is filled once by StaticInitialization and never written
// again, so every lookup below goes through find(). std::map::operator[] does
// not: on a label that was never registered it inserts a value-initialized
// EMDLabelData, whose user-provided default constructor leaves `type`
// indeterminate -- so the old isInt()/isDouble()/... answered from an
// uninitialized enum, and did it by mutating a global that two threads may be
// reading. Both are why these take a const_iterator now.
namespace
{
EMDLabelType labelType(const std::map<EMDLabel, EMDLabelData> &data,
                       const EMDLabel &label, bool &found)
{
    const std::map<EMDLabel, EMDLabelData>::const_iterator it = data.find(label);
    found = (it != data.end());
    return found ? it->second.type : EMDL_UNKNOWN;
}
}

EMDLabel  EMDL::str2Label(const std::string &labelName)
{
    const std::map<std::string, EMDLabel>::const_iterator it = names.find(labelName);
    if (it == names.end())
        return EMDL_UNDEFINED;
    return it->second;
}//close function str2Label

std::string  EMDL::label2Str(const EMDLabel &label)
{
    const std::map<EMDLabel, EMDLabelData>::const_iterator it = data.find(label);
    if (it == data.end())
            return "";
    return it->second.str;
}//close function label2Str

bool EMDL::isInt(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_INT;
}
bool EMDL::isBool(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_BOOL;
}
bool EMDL::isString(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_STRING;
}
bool EMDL::isDouble(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_DOUBLE;
}
bool EMDL::isNumber(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && (type == EMDL_DOUBLE || type == EMDL_INT);
}
bool EMDL::isIntVector(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_INT_VECTOR;
}
bool EMDL::isDoubleVector(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_DOUBLE_VECTOR;
}
bool EMDL::isVector(const EMDLabel &label)
{
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && (type == EMDL_DOUBLE_VECTOR || type == EMDL_INT_VECTOR);
}
bool EMDL::isUnknown(const EMDLabel &label)
{
    // An unregistered label is not an EMDL_UNKNOWN-typed one: the caller asks
    // what the registry says the type is, and for a missing label it says
    // nothing.
    bool found = false;
    const EMDLabelType type = labelType(data, label, found);
    return found && type == EMDL_UNKNOWN;
}

bool EMDL::isValidLabel(const EMDLabel &label)
{
    return (label > EMDL_UNDEFINED && label < EMDL_LAST_LABEL);
}
bool EMDL::isValidLabel(const std::string &labelName)
{
    EMDLabel label = EMDL::str2Label(labelName);
    return EMDL::isValidLabel(label);
}

