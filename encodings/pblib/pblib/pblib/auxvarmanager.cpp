#include "auxvarmanager.h"

#include <iostream>
#include <limits>
#include <stdexcept>

using namespace std;

int32_t AuxVarManager::getBiggestReturnedAuxVar()
{
  return static_cast<int32_t>(variable_offset - 1);
}

void AuxVarManager::resetAuxVarsTo(int32_t new_first_free_variable)
{
    variable_offset = new_first_free_variable;

	// removing all variables from free variables that are obsolet now
    for (auto it = free_variables.begin(); it != free_variables.end(); )
	{
        if (*it >= variable_offset)
		{
            free_variables.erase(it++);
        }
        else
		{
            ++it;
        }
    }
}


void AuxVarManager::freeVariables(int32_t start, int32_t end)
{
  for (int64_t var = start; var <= end; ++var)
    freeVariable(static_cast<int32_t>(var));
}

void AuxVarManager::freeVariables(vector< int32_t >& variables)
{
  for (int i = 0; i < variables.size(); ++i)
    freeVariable(variables[i]);
}


void AuxVarManager::freeVariable(int32_t var)
{
  free_variables.insert(var);
}

int32_t AuxVarManager::getVariable()
{
  int32_t var;
  if (free_variables.size() == 0)
  {
    if (variable_offset > std::numeric_limits<int32_t>::max())
      throw std::overflow_error("PB auxiliary variable IDs exceed signed 32-bit range");
    var = static_cast<int32_t>(variable_offset);
    variable_offset++;
    if (rememberedVariables != nullptr)
      rememberedVariables->push_back(var);

    return var;
  }


  var = *free_variables.begin();
  free_variables.erase(free_variables.begin());

  if (rememberedVariables != nullptr)
      rememberedVariables->push_back(var);

  return var;
}


void AuxVarManager::startRememberReturnedVariables(vector< int32_t > * variables)
{
  rememberedVariables = variables;
}

void AuxVarManager::stopRememerReturnedVariables()
{
  rememberedVariables = nullptr;
}


AuxVarManager::AuxVarManager(int64_t first_free_variable) : variable_offset(first_free_variable), rememberedVariables(nullptr)
{
}
